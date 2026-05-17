#!/usr/bin/env python3
"""Minimal cached LLM client for deterministic resume pipeline stages."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from ._runtime_guard import assert_not_blocked_runtime_input

_DEFAULT_CHAT_ENDPOINT = "http://localhost:11434/v1/chat/completions"
_DEFAULT_MODEL = "llama3.1:8b"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_FIXTURE_ENV = "RESUME_BUILDER_LLM_FIXTURE"
_CACHE_DIR_ENV = "RESUME_BUILDER_LLM_CACHE_DIR"
_ENDPOINT_ENV = "RESUME_BUILDER_LLM_API_URL"
_MODEL_ENV = "RESUME_BUILDER_LLM_MODEL"
_TIMEOUT_ENV = "RESUME_BUILDER_LLM_TIMEOUT_SECONDS"


def _parse_timeout_env(raw: str | None) -> float:
    """Parse RESUME_BUILDER_LLM_TIMEOUT_SECONDS, falling back to the default.

    Empty / unset / non-numeric values fall back to the default; values
    <= 0 also fall back since urlopen requires a positive timeout (or
    None, but we don't expose 'no timeout' as a knob).
    """
    if raw is None:
        return _DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw.strip())
    except ValueError:
        return _DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        return _DEFAULT_TIMEOUT_SECONDS
    return value


@dataclass(frozen=True)
class LLMResponse:
    content: str
    cache_key: str
    from_cache: bool


class LLMClient:
    """OpenAI-compatible chat client with file cache and fixture mode."""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        cache_dir: Path,
        fixture_mode: bool,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._endpoint = endpoint
        self._model = model
        self._cache_dir = cache_dir
        self._fixture_mode = fixture_mode
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> LLMClient:
        fixture_mode = os.getenv(_FIXTURE_ENV, "0").strip() == "1"
        default_cache_dir = "tests/fixtures/llm_cache" if fixture_mode else ".llm_cache"
        cache_dir = Path(
            os.getenv(_CACHE_DIR_ENV, default_cache_dir).strip() or default_cache_dir
        )
        endpoint = os.getenv(_ENDPOINT_ENV, _DEFAULT_CHAT_ENDPOINT).strip()
        model = os.getenv(_MODEL_ENV, _DEFAULT_MODEL).strip() or _DEFAULT_MODEL
        timeout_seconds = _parse_timeout_env(os.getenv(_TIMEOUT_ENV))
        return cls(
            endpoint=endpoint,
            model=model,
            cache_dir=cache_dir,
            fixture_mode=fixture_mode,
            timeout_seconds=timeout_seconds,
        )

    def complete_json(
        self,
        *,
        namespace: str,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, Any]:
        """Return a parsed JSON object from the LLM.

        Error contract (callers may rely on this for narrowed fallback
        handlers):
          - ``ValueError`` for response-shape failures: invalid JSON,
            non-object JSON, or malformed cache payload.
          - ``RuntimeError`` for every other recoverable failure path:
            transport errors (network / DNS / timeout / connection reset),
            cache filesystem I/O errors, fixture-mode misses, and
            malformed upstream chat-completion responses.

        Callers should catch ``(RuntimeError, ValueError)`` to degrade
        gracefully; anything else escaping from here is a real bug.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, sort_keys=True)},
        ]
        response = self._chat(messages=messages, namespace=namespace)
        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM response was not valid JSON for namespace={namespace} "
                f"cache_key={response.cache_key}"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"LLM JSON response must be an object for namespace={namespace} "
                f"cache_key={response.cache_key}"
            )
        return parsed

    def _chat(self, *, messages: list[dict[str, str]], namespace: str) -> LLMResponse:
        cache_key = self._cache_key(messages=messages, namespace=namespace)
        cache_path = self._cache_dir / f"llm_response_{cache_key}.json"
        assert_not_blocked_runtime_input(cache_path)

        try:
            cached = self._read_cache(cache_path)
        except OSError as exc:
            # Normalize cache-read filesystem failures (permission denied,
            # unreadable file, etc.) into RuntimeError so callers that catch
            # (RuntimeError, ValueError) around complete_json continue to get
            # the documented fallback behavior instead of an unexpected
            # OSError propagating out.
            raise RuntimeError(
                f"LLM cache read failed for namespace={namespace} "
                f"cache_key={cache_key}: {exc}"
            ) from exc
        if cached is not None:
            return LLMResponse(content=cached, cache_key=cache_key, from_cache=True)

        if self._fixture_mode:
            raise RuntimeError(
                f"LLM fixture missing for namespace={namespace} cache_key={cache_key}"
            )

        content = self._request_chat_completion(messages)
        try:
            self._write_cache(cache_path=cache_path, content=content)
        except OSError as exc:
            # Same rationale as the read path above: a disk/permission failure
            # writing the cache must not bypass callers' (RuntimeError,
            # ValueError) handlers.
            raise RuntimeError(
                f"LLM cache write failed for namespace={namespace} "
                f"cache_key={cache_key}: {exc}"
            ) from exc
        return LLMResponse(content=content, cache_key=cache_key, from_cache=False)

    def _cache_key(self, *, messages: list[dict[str, str]], namespace: str) -> str:
        payload = {
            "namespace": namespace,
            "model": self._model,
            "messages": messages,
            "endpoint": self._endpoint,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _request_chat_completion(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # nosec B310
                body = response.read().decode("utf-8", errors="replace")
        except (OSError, TimeoutError) as exc:
            # urllib.error.URLError and socket.timeout both inherit from
            # OSError, and response.read() can also raise raw OSError /
            # TimeoutError mid-stream. Normalize all transport-level
            # failures to RuntimeError so callers that catch
            # (RuntimeError, ValueError) around complete_json (per its
            # docstring contract) keep the documented fallback behavior
            # instead of being aborted by an unexpected OSError.
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM response was not valid JSON") from exc

        choices = decoded.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("LLM response choice was malformed")
        message = first.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("LLM response message was malformed")
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM response content was empty")
        return content

    def _read_cache(self, path: Path) -> str | None:
        if not path.exists():
            return None
        assert_not_blocked_runtime_input(path)
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("LLM cache payload must be an object")
        content = payload.get("content")
        if not isinstance(content, str):
            raise ValueError("LLM cache payload missing content string")
        return content

    def _write_cache(self, *, cache_path: Path, content: str) -> None:
        assert_not_blocked_runtime_input(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "model": self._model,
            "endpoint": self._endpoint,
            "content": content,
        }
        cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
