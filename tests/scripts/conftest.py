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

import hashlib
import sys
from pathlib import Path

import pytest

# Workaround for tooling#470: synced test files (`tests/scripts/test_check_*.py`)
# use bare `from _helpers import isolated_git_env`. That works in tooling
# (no `tests/__init__.py`, pytest auto-adds `tests/scripts/` to sys.path
# under rootdir-mode). This consumer has `tests/__init__.py` +
# `tests/scripts/__init__.py` making it a package, so pytest does NOT
# add `tests/scripts/` to sys.path. Insert it explicitly so the bare
# imports resolve. Remove this once tooling#470 ships a relative-import
# fix and the next sync pulls it in.
sys.path.insert(0, str(Path(__file__).parent))

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_PROFILE = _REPO_ROOT / "data" / "profile" / "profile.toml"
_FIXTURE_PROFILE = (
    _REPO_ROOT / "tests" / "fixtures" / "profile" / "profile_baseline.toml"
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="session", autouse=True)
def _ensure_default_profile_for_cli_tests() -> object:
    """Seed the default profile path with a tracked synthetic baseline.

    Only writes when the runtime profile is absent; existing real profiles
    are preserved untouched. On teardown, removes the seeded copy only if
    its content still matches what we wrote — so if a contributor or test
    replaced it with real content during the session, we leave that file
    alone instead of deleting their work.
    """
    seeded_sha: str | None = None
    if not _RUNTIME_PROFILE.exists():
        _RUNTIME_PROFILE.parent.mkdir(parents=True, exist_ok=True)
        seeded_bytes = _FIXTURE_PROFILE.read_bytes()
        _RUNTIME_PROFILE.write_bytes(seeded_bytes)
        seeded_sha = _sha256(seeded_bytes)
    yield
    if seeded_sha is None or not _RUNTIME_PROFILE.exists():
        return
    if _sha256(_RUNTIME_PROFILE.read_bytes()) == seeded_sha:
        _RUNTIME_PROFILE.unlink()
