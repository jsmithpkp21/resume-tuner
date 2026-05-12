"""Tests for the per-ATS credential store (issue #333)."""

from __future__ import annotations

import stat
import tomllib
from datetime import date
from pathlib import Path

import pytest

from resume_builder import credential_store


def _credentials_path(tmp_path: Path) -> Path:
    return tmp_path / "applications" / "credentials.toml"


class TestLookup:
    """Behavior of :func:`credential_store.lookup`."""

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        assert credential_store.lookup("workday", "becu", path=path) is None

    def test_returns_none_when_ats_missing(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("workday", "becu", "u@example.com", "pw", path=path)
        assert credential_store.lookup("workable", "x", path=path) is None

    def test_returns_none_when_tenant_missing(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("workday", "becu", "u@example.com", "pw", path=path)
        assert credential_store.lookup("workday", "other", path=path) is None

    def test_round_trip(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record(
            "workday",
            "becu",
            "user@example.com",
            "secret",
            tenant_url="https://becu.wd1.myworkdayjobs.com/External",
            notes="initial record",
            created=date(2026, 5, 11),
            path=path,
        )
        entry = credential_store.lookup("workday", "becu", path=path)
        assert entry is not None
        assert entry["username"] == "user@example.com"
        assert entry["password"] == "secret"
        assert entry["tenant_url"] == "https://becu.wd1.myworkdayjobs.com/External"
        assert entry["notes"] == "initial record"
        assert entry["created"] == date(2026, 5, 11)

    def test_key_normalization_is_case_insensitive(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("Workday", "BECU", "u@example.com", "pw", path=path)
        # Both casing variants resolve to the same normalized slug.
        assert credential_store.lookup("workday", "becu", path=path) is not None
        assert credential_store.lookup("WORKDAY", "Becu", path=path) is not None


class TestRecord:
    """Behavior of :func:`credential_store.record`."""

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "applications" / "credentials.toml"
        credential_store.record("workday", "becu", "u@example.com", "pw", path=path)
        assert path.exists()

    def test_file_mode_is_0600(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("workday", "becu", "u@example.com", "pw", path=path)
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"

    def test_preserves_other_tenants_on_update(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("workday", "becu", "u1@example.com", "pw1", path=path)
        credential_store.record(
            "workday", "westernunion", "u2@example.com", "pw2", path=path
        )
        # Update becu — westernunion must survive untouched.
        credential_store.record(
            "workday",
            "becu",
            "u1-new@example.com",
            "pw1-new",
            path=path,
        )
        becu = credential_store.lookup("workday", "becu", path=path)
        wu = credential_store.lookup("workday", "westernunion", path=path)
        assert becu is not None and becu["username"] == "u1-new@example.com"
        assert becu["password"] == "pw1-new"
        assert wu is not None and wu["username"] == "u2@example.com"
        assert wu["password"] == "pw2"

    def test_preserves_other_ats_families(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record("workday", "becu", "u1@example.com", "pw1", path=path)
        credential_store.record(
            "workable",
            "murmuration",
            "u2@example.com",
            "pw2",
            path=path,
        )
        assert credential_store.lookup("workday", "becu", path=path) is not None
        assert credential_store.lookup("workable", "murmuration", path=path) is not None

    def test_default_created_is_today(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        before = date.today()
        credential_store.record("workday", "becu", "u@example.com", "pw", path=path)
        after = date.today()
        entry = credential_store.lookup("workday", "becu", path=path)
        assert entry is not None
        assert before <= entry["created"] <= after

    def test_writes_valid_toml(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        credential_store.record(
            "workday",
            "becu",
            "u@example.com",
            'pw with "quote" and \\ backslash',
            notes="line1\nline2",
            path=path,
        )
        # tomllib must round-trip the file we wrote.
        with path.open("rb") as fh:
            parsed = tomllib.load(fh)
        entry = parsed["ats"]["workday"]["becu"]
        assert entry["password"] == 'pw with "quote" and \\ backslash'
        assert entry["notes"] == "line1\nline2"


class TestNormalizeKey:
    """Behavior of the private key-normalizer (covered via public API)."""

    def test_empty_input_raises(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        with pytest.raises(ValueError):
            credential_store.record("", "becu", "u@example.com", "pw", path=path)
        with pytest.raises(ValueError):
            credential_store.record("workday", "  ", "u@example.com", "pw", path=path)

    def test_punctuation_only_input_raises(self, tmp_path: Path) -> None:
        path = _credentials_path(tmp_path)
        with pytest.raises(ValueError):
            credential_store.record("---", "becu", "u@example.com", "pw", path=path)


def test_default_path_under_repo_root() -> None:
    """The default credentials path resolves under ``data/applications/``."""
    default = credential_store.DEFAULT_CREDENTIALS_PATH
    assert default.name == "credentials.toml"
    assert default.parent.name == "applications"
    assert default.parent.parent.name == "data"
