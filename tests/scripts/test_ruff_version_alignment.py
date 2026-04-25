#!/usr/bin/env python3
"""Guard against Ruff version drift between local env and pre-commit hooks."""

from pathlib import Path

import yaml

REPO_ROOT: Path = Path(__file__).parent.parent.parent.resolve()


def _read_requirements_ruff_version() -> str:
    requirements = (
        (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    )
    for line in requirements:
        line = line.strip()
        if line.startswith("ruff=="):
            return line.split("==", maxsplit=1)[1]
    raise AssertionError("ruff pin not found in requirements-dev.txt")


def _read_precommit_ruff_version() -> str:
    config_path = REPO_ROOT / ".pre-commit-config.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for repo in config.get("repos", []):
        if repo.get("repo") == "https://github.com/astral-sh/ruff-pre-commit":
            rev = repo.get("rev", "")
            if not rev:
                raise AssertionError("ruff-pre-commit rev is missing")
            return str(rev).lstrip("v")
    raise AssertionError("ruff-pre-commit repo not found in .pre-commit-config.yaml")


def test_ruff_versions_are_aligned() -> None:
    """Ensure requirements-dev and pre-commit use the same Ruff version pin."""
    req_version = _read_requirements_ruff_version()
    precommit_version = _read_precommit_ruff_version()
    assert req_version == precommit_version, (
        "Ruff version drift detected: "
        f"requirements-dev.txt has {req_version}, "
        f".pre-commit-config.yaml has {precommit_version}. "
        "Keep these pinned to the same version."
    )
