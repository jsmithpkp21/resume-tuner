from __future__ import annotations

import json
from pathlib import Path

import pytest

from resume_builder.llm_client import (
    _DEFAULT_TIMEOUT_SECONDS,
    LLMClient,
    _parse_timeout_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_complete_json_reads_cached_fixture_in_fixture_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")

    client = LLMClient.from_env()
    user_payload: dict[str, object] = {"value": 1}
    messages = [
        {"role": "system", "content": "Return JSON."},
        {"role": "user", "content": json.dumps(user_payload, sort_keys=True)},
    ]
    cache_key = client._cache_key(messages=messages, namespace="trim_for_role")
    cache_path = tmp_path / f"llm_response_{cache_key}.json"
    cache_path.write_text(
        json.dumps({"content": '{"scores": [{"id": "b1", "score": 0.8}]}'}) + "\n",
        encoding="utf-8",
    )

    parsed = client.complete_json(
        namespace="trim_for_role",
        system_prompt="Return JSON.",
        user_payload=user_payload,
    )

    assert parsed == {"scores": [{"id": "b1", "score": 0.8}]}


def test_complete_json_fixture_mode_missing_fixture_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")

    client = LLMClient.from_env()

    with pytest.raises(RuntimeError, match="fixture missing"):
        client.complete_json(
            namespace="trim_for_role",
            system_prompt="Return JSON.",
            user_payload={"value": 1},
        )


def test_complete_json_rejects_blocked_cache_dir_before_file_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_CACHE_DIR",
        str(REPO_ROOT / "data" / "samples" / "llm_cache"),
    )
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")

    client = LLMClient.from_env()

    with pytest.raises(ValueError, match="blocked runtime directory"):
        client.complete_json(
            namespace="trim_for_role",
            system_prompt="Return JSON.",
            user_payload={"value": 1},
        )


def test_complete_json_normalizes_cache_read_oserror_to_runtimeerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")

    client = LLMClient.from_env()

    def _raise_oserror(self: LLMClient, path: Path) -> str | None:  # noqa: ARG001
        raise PermissionError("simulated cache read failure")

    monkeypatch.setattr(LLMClient, "_read_cache", _raise_oserror, raising=True)

    with pytest.raises(RuntimeError, match="cache read failed"):
        client.complete_json(
            namespace="trim_for_role",
            system_prompt="Return JSON.",
            user_payload={"value": 1},
        )


@pytest.mark.parametrize(
    "transport_exc",
    [
        pytest.param(
            __import__("urllib.error", fromlist=["URLError"]).URLError("dns failure"),
            id="urllib-urlerror",
        ),
        pytest.param(TimeoutError("read timed out"), id="builtin-timeouterror"),
        pytest.param(
            ConnectionResetError("connection reset by peer"),
            id="connection-reset",
        ),
        pytest.param(OSError("network unreachable"), id="bare-oserror"),
    ],
)
def test_complete_json_normalizes_transport_errors_to_runtimeerror(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    transport_exc: BaseException,
) -> None:
    # Live (non-fixture) mode so _request_chat_completion runs; cache_dir
    # points at an empty tmp_path so the cached-hit short-circuit is skipped
    # and we actually exercise the urlopen code path.
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")

    client = LLMClient.from_env()

    def _raise_transport(*_args: object, **_kwargs: object) -> None:
        raise transport_exc

    monkeypatch.setattr(
        "resume_builder.llm_client.urlopen", _raise_transport, raising=True
    )

    with pytest.raises(RuntimeError, match="LLM request failed"):
        client.complete_json(
            namespace="trim_for_role",
            system_prompt="Return JSON.",
            user_payload={"value": 1},
        )


@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, _DEFAULT_TIMEOUT_SECONDS),
        ("", _DEFAULT_TIMEOUT_SECONDS),
        ("not-a-number", _DEFAULT_TIMEOUT_SECONDS),
        ("0", _DEFAULT_TIMEOUT_SECONDS),
        ("-5", _DEFAULT_TIMEOUT_SECONDS),
        ("60", 60.0),
        ("600", 600.0),
        ("  120  ", 120.0),
        ("90.5", 90.5),
    ],
)
def test_parse_timeout_env_parses_or_falls_back_to_default(
    raw: str | None, expected: float
) -> None:
    assert _parse_timeout_env(raw) == expected


def test_from_env_uses_timeout_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    client = LLMClient.from_env()
    # Internal attribute, but it's the only way to verify the env wired through
    # without making an actual network request.
    assert client._timeout_seconds == 180.0  # noqa: SLF001 -- intentional


def test_from_env_default_timeout_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    client = LLMClient.from_env()
    assert client._timeout_seconds == _DEFAULT_TIMEOUT_SECONDS  # noqa: SLF001


# --- response_schema (#436) ----------------------------------------------


def _make_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LLMClient:
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv(
        "RESUME_BUILDER_LLM_API_URL", "http://localhost:11434/v1/chat/completions"
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_MODEL", "llama3.1:8b")
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    return LLMClient.from_env()


def test_request_payload_omits_json_schema_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `response_schema` -> request keeps the legacy weak json_object mode."""
    client = _make_client(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_urlopen(req: object, timeout: float) -> object:  # noqa: ARG001
        captured["data"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]

        class _Resp:
            def __enter__(self) -> object:
                return self

            def __exit__(self, *a: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {"choices": [{"message": {"content": '{"ok": true}'}}]}
                ).encode("utf-8")

        return _Resp()

    monkeypatch.setattr("resume_builder.llm_client.urlopen", fake_urlopen)
    client.complete_json(namespace="t", system_prompt="s", user_payload={"k": "v"})
    assert captured["data"]["response_format"] == {"type": "json_object"}  # type: ignore[index]


def test_request_payload_includes_json_schema_when_provided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With `response_schema` -> request uses OpenAI-compat strict json_schema."""
    client = _make_client(tmp_path, monkeypatch)
    captured: dict[str, object] = {}

    def fake_urlopen(req: object, timeout: float) -> object:  # noqa: ARG001
        captured["data"] = json.loads(req.data.decode("utf-8"))  # type: ignore[attr-defined]

        class _Resp:
            def __enter__(self) -> object:
                return self

            def __exit__(self, *a: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {"choices": [{"message": {"content": '{"opening": "x"}'}}]}
                ).encode("utf-8")

        return _Resp()

    monkeypatch.setattr("resume_builder.llm_client.urlopen", fake_urlopen)
    schema = {
        "name": "cl_body",
        "schema": {
            "type": "object",
            "properties": {"opening": {"type": "string"}},
            "required": ["opening"],
            "additionalProperties": False,
        },
    }
    client.complete_json(
        namespace="t",
        system_prompt="s",
        user_payload={"k": "v"},
        response_schema=schema,
    )
    rf = captured["data"]["response_format"]  # type: ignore[index]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "cl_body"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["required"] == ["opening"]


def test_cache_key_differs_when_schema_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same prompt + different schema must hash to different cache keys —
    the model's output can legitimately differ, so they're not the same
    response.
    """
    client = _make_client(tmp_path, monkeypatch)
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": '{"k":"v"}'},
    ]
    key_none = client._cache_key(  # noqa: SLF001
        messages=messages, namespace="t", response_schema=None
    )
    key_schema_a = client._cache_key(  # noqa: SLF001
        messages=messages,
        namespace="t",
        response_schema={"name": "a", "schema": {"type": "object"}},
    )
    key_schema_b = client._cache_key(  # noqa: SLF001
        messages=messages,
        namespace="t",
        response_schema={"name": "b", "schema": {"type": "object"}},
    )
    assert key_none != key_schema_a
    assert key_schema_a != key_schema_b
