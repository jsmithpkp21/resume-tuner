"""Tests for `job_apply_kit.io_safety`.

The module is small but is the single trust boundary for CLI-supplied slug
values (interpolated into filenames) and the only path through which
session drivers write JSON captures atomically. The previous coverage gap
(~42%) reflected that nothing exercised either helper.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from job_apply_kit.io_safety import atomic_write_json, sanitize_slug

# ---------------------------------------------------------------------------
# sanitize_slug
# ---------------------------------------------------------------------------


def test_sanitize_slug_accepts_typical_capture_naming() -> None:
    """Real `<seq>-<company>-<role>` capture slugs round-trip unchanged."""
    assert sanitize_slug("01-becu-staff-sdet") == "01-becu-staff-sdet"


def test_sanitize_slug_accepts_alphanumeric_with_underscore_and_dash() -> None:
    assert sanitize_slug("abc_123-XYZ") == "abc_123-XYZ"


def test_sanitize_slug_rejects_empty_string() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        sanitize_slug("")


def test_sanitize_slug_rejects_path_separator() -> None:
    with pytest.raises(ValueError, match="disallowed characters"):
        sanitize_slug("foo/bar")


def test_sanitize_slug_rejects_backslash() -> None:
    with pytest.raises(ValueError, match="disallowed characters"):
        sanitize_slug("foo\\bar")


def test_sanitize_slug_rejects_parent_dir_reference() -> None:
    with pytest.raises(ValueError, match="disallowed characters"):
        sanitize_slug("..")


def test_sanitize_slug_rejects_leading_dash() -> None:
    """Leading `-` would be ambiguous as a CLI flag downstream."""
    with pytest.raises(ValueError, match="disallowed characters"):
        sanitize_slug("-leading-dash")


def test_sanitize_slug_rejects_space() -> None:
    with pytest.raises(ValueError, match="disallowed characters"):
        sanitize_slug("foo bar")


def test_sanitize_slug_rejects_overlong_value() -> None:
    """81-char slug exceeds the 80-char cap."""
    with pytest.raises(ValueError, match="must be"):
        sanitize_slug("a" * 81)


def test_sanitize_slug_accepts_max_length() -> None:
    """Exactly 80 chars is allowed (boundary value)."""
    s = "a" * 80
    assert sanitize_slug(s) == s


# ---------------------------------------------------------------------------
# atomic_write_json
# ---------------------------------------------------------------------------


def test_atomic_write_json_writes_payload(tmp_path: Path) -> None:
    target = tmp_path / "snapshot.json"
    payload = {"fields": [{"label": "First Name"}], "count": 1}
    atomic_write_json(target, payload)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_atomic_write_json_creates_parent_dirs(tmp_path: Path) -> None:
    """Drivers may target nested capture dirs that don't yet exist."""
    target = tmp_path / "capture" / "session-1" / "snap.json"
    atomic_write_json(target, [1, 2, 3])
    assert target.parent.is_dir()
    assert json.loads(target.read_text(encoding="utf-8")) == [1, 2, 3]


def test_atomic_write_json_overwrites_existing_file_atomically(
    tmp_path: Path,
) -> None:
    """`os.replace` semantics: a stale snapshot is replaced atomically with new content."""
    target = tmp_path / "snap.json"
    target.write_text(json.dumps({"old": True}), encoding="utf-8")
    atomic_write_json(target, {"new": True})
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


def test_atomic_write_json_does_not_leave_tmp_artifacts(tmp_path: Path) -> None:
    """Successful writes must not leave `.<name>.*.tmp` siblings behind."""
    target = tmp_path / "snap.json"
    atomic_write_json(target, {"k": "v"})
    siblings = [p.name for p in tmp_path.iterdir()]
    assert siblings == ["snap.json"], (
        f"unexpected sibling files after atomic write: {siblings}"
    )


def test_atomic_write_json_preserves_unicode_without_escaping(tmp_path: Path) -> None:
    """`ensure_ascii=False`: non-ASCII characters stay literal in the on-disk JSON."""
    target = tmp_path / "snap.json"
    atomic_write_json(target, {"name": "café"})
    raw = target.read_text(encoding="utf-8")
    assert "café" in raw
    # No é escape sequence — confirms ensure_ascii=False is honored.
    assert "\\u00e9" not in raw


def test_atomic_write_json_indents_output(tmp_path: Path) -> None:
    """Drop-in replacement for `Path.write_text(json.dumps(..., indent=2))`."""
    target = tmp_path / "snap.json"
    atomic_write_json(target, {"a": 1, "b": [1, 2]})
    raw = target.read_text(encoding="utf-8")
    # indent=2 produces newlines and two-space leading indents
    assert "\n" in raw
    assert '  "a": 1' in raw


def test_atomic_write_json_temp_file_is_in_same_directory_to_keep_replace_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp file must be created in `path.parent` so `os.replace` is atomic.

    `os.replace` requires the source and destination to live on the same
    filesystem; a cross-filesystem call raises `OSError` (EXDEV) rather than
    falling back to copy+delete. Keeping the temp file in the target
    directory avoids that error and preserves the rename's atomicity.
    """
    target = tmp_path / "snap.json"
    seen_dirs: list[str] = []

    real_named_temp = __import__("tempfile").NamedTemporaryFile

    def spy(*args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        seen_dirs.append(str(kwargs.get("dir")))
        return real_named_temp(*args, **kwargs)

    monkeypatch.setattr("job_apply_kit.io_safety.tempfile.NamedTemporaryFile", spy)
    atomic_write_json(target, {"k": "v"})
    assert seen_dirs == [str(tmp_path)]


def test_atomic_write_json_fsyncs_before_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirm `os.fsync` is invoked on the temp file before the rename.

    Without fsync, the kernel can lose the data on power-loss even after
    the rename returns; the helper exists specifically to provide that
    guarantee, so coverage should pin it.
    """
    called: list[int] = []
    real_fsync = os.fsync

    def spy_fsync(fd: int) -> None:
        called.append(fd)
        real_fsync(fd)

    monkeypatch.setattr("job_apply_kit.io_safety.os.fsync", spy_fsync)
    atomic_write_json(tmp_path / "snap.json", {"k": "v"})
    assert len(called) == 1
