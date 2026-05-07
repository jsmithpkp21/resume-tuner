"""Pytest fixtures for the scripts test suite.

Subprocess CLI tests invoke ``scripts/build_resume.py`` from the repo root
without ``--profile``, falling back to ``DEFAULT_PROFILE`` at
``data/profile/profile.toml``. That path is per-contributor runtime input
(gitignored) and absent in a fresh clone or CI checkout, so an autouse
session fixture seeds it from the tracked synthetic baseline at
``tests/fixtures/profile/profile_baseline.toml`` when missing — and
restores the original state on teardown so a contributor's real
``profile.toml`` is never overwritten.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_PROFILE = _REPO_ROOT / "data" / "profile" / "profile.toml"
_FIXTURE_PROFILE = (
    _REPO_ROOT / "tests" / "fixtures" / "profile" / "profile_baseline.toml"
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_default_profile_for_cli_tests() -> object:
    """Seed the default profile path with a tracked synthetic baseline.

    Only writes when the runtime profile is absent; existing real profiles
    are preserved untouched. Removes the seeded copy on teardown.
    """
    seeded = False
    if not _RUNTIME_PROFILE.exists():
        _RUNTIME_PROFILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_FIXTURE_PROFILE, _RUNTIME_PROFILE)
        seeded = True
    yield
    if seeded and _RUNTIME_PROFILE.exists():
        _RUNTIME_PROFILE.unlink()
