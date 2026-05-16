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
