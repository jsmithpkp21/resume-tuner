#!/usr/bin/env python3
"""Regression tests for exact workflow action pin enforcement."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT: Path = Path(__file__).parent.parent.parent.resolve()
WORKFLOW_DIR: Path = REPO_ROOT / ".github" / "workflows"
LOCK_FILE: Path = REPO_ROOT / ".github" / "workflow-action-lock.json"
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")


def _load_workflow(path: Path) -> dict[str, Any]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), f"Workflow file is not a mapping: {path}"
    return parsed


def _load_lock() -> dict[str, str]:
    assert LOCK_FILE.exists(), f"Missing action lock file: {LOCK_FILE}"
    payload = json.loads(LOCK_FILE.read_text(encoding="utf-8"))
    schema_version = payload.get("schema_version")
    assert isinstance(schema_version, int), "Lock schema_version must be an int"
    assert schema_version == 1, f"Unsupported lock schema_version: {schema_version}"
    actions = payload.get("actions")
    assert isinstance(actions, dict) and actions, (
        "Lock file must define non-empty actions map"
    )
    typed: dict[str, str] = {}
    for action, ref in actions.items():
        assert isinstance(action, str), "Lock action names must be strings"
        assert isinstance(ref, str), "Lock refs must be strings"
        assert "@" not in action, f"Lock action keys must not include @ref: {action}"
        typed[action] = ref
    return typed


def _iter_external_uses_refs(workflow_path: Path) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for line in workflow_path.read_text(encoding="utf-8").splitlines():
        match = USES_RE.match(line)
        if not match:
            continue
        uses_value = match.group(1)
        if uses_value.startswith("./") or "@" not in uses_value:
            continue
        action, ref = uses_value.split("@", 1)
        refs.append((action, ref))
    return refs


def test_action_lock_schema() -> None:
    lock = _load_lock()
    assert lock, "Action lock must contain at least one action pin"


def test_workflow_action_refs_match_lock_exactly() -> None:
    lock = _load_lock()
    workflow_files = sorted(
        list(WORKFLOW_DIR.glob("*.yml")) + list(WORKFLOW_DIR.glob("*.yaml"))
    )
    assert workflow_files, f"No workflow files found in {WORKFLOW_DIR}"

    seen_actions: set[str] = set()

    for workflow_path in workflow_files:
        _load_workflow(workflow_path)
        for action, ref in _iter_external_uses_refs(workflow_path):
            seen_actions.add(action)
            assert action in lock, (
                f"{workflow_path.name}: action {action}@{ref} is not declared in "
                f"{LOCK_FILE.relative_to(REPO_ROOT)}"
            )
            assert ref == lock[action], (
                f"{workflow_path.name}: action {action}@{ref} does not match locked "
                f"ref {lock[action]}"
            )

    missing = sorted(set(lock) - seen_actions)
    assert not missing, f"Lock contains unused action entries: {', '.join(missing)}"
