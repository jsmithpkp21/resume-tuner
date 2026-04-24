from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_hooks(config: dict[str, Any], hook_id: str) -> list[dict[str, Any]]:
    return [
        hook
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("id") == hook_id
    ]


def test_precommit_has_push_stage_full_repo_quality_hooks() -> None:
    config_path = REPO_ROOT / ".pre-commit-config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    ruff_hooks = _find_hooks(config, "ruff")
    assert any(
        hook.get("name") == "ruff-check-all"
        and hook.get("pass_filenames") is False
        and "push" in hook.get("stages", [])
        and hook.get("args") == ["."]
        for hook in ruff_hooks
    )

    format_hooks = _find_hooks(config, "ruff-format")
    assert any(
        hook.get("name") == "ruff-format-check-all"
        and hook.get("pass_filenames") is False
        and "push" in hook.get("stages", [])
        and hook.get("args") == ["--check", "."]
        for hook in format_hooks
    )


def test_repo_tests_do_not_include_non_ruff_signature_annotation_pattern() -> None:
    """Guard against recurring test-format regressions by running Ruff check."""
    files = [
        "tests/scripts/test_build_resume.py",
        "tests/scripts/test_export_resume_documents.py",
        "tests/scripts/test_pr_review_helper.py",
        "tests/scripts/test_select_skills.py",
    ]
    result = subprocess.run(
        ["ruff", "format", "--check", *files],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        "Ruff format check failed for high-churn tests. "
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
