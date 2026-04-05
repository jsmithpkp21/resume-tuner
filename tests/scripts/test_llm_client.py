from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.llm_client import LLMClient


def test_complete_json_reads_cached_fixture_in_fixture_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.setenv("RESUME_BUILDER_LLM_CACHE_DIR", str(tmp_path))

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

    client = LLMClient.from_env()

    with pytest.raises(RuntimeError, match="fixture missing"):
        client.complete_json(
            namespace="trim_for_role",
            system_prompt="Return JSON.",
            user_payload={"value": 1},
        )
