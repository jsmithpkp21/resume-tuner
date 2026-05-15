"""Tests for `scripts/check_makefile_bash_quoting.py`."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_makefile_bash_quoting.py"
_spec = importlib.util.spec_from_file_location(
    "check_makefile_bash_quoting", _SCRIPT_PATH
)
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


class TestIsOffender:
    """Pure-function core: does a single (joined) line match the danger pattern?"""

    @pytest.mark.parametrize(
        "line",
        [
            '\tbash -lc "echo $$FOO"',
            '\tbash -c "echo $$FOO"',
            '\tbash -lc "echo $${FOO:+default}"',
            '\tbash -lc "source x && python3 y $${VAR:+\\"$$VAR\\"}"',
            '\t@bash -lc "echo $$FOO"',
        ],
    )
    def test_offending_patterns_caught(self, line: str) -> None:
        assert mod._is_offender(line) is True

    @pytest.mark.parametrize(
        "line",
        [
            "\tbash -lc 'echo $$FOO'",  # single-quoted outer → safe
            '\tbash -lc "source $(ENV_PATH)/bin/activate"',  # only make-var
            "\techo hello",  # no bash -lc at all
            "\techo $$HOME",  # $$VAR outside bash -lc
            '\tpython3 -c "print(\\"$VAR\\")"',  # python -c, not bash
            "\tbash -lc 'mixed \"quoted\" parts but $$VAR is in single quotes'",
            '\tbash -lc "echo $$1"',  # positional $1 — shell-set, not user input
            '\tbash -lc "echo $$@"',  # all args — shell-set
            '\tbash -lc "echo $$!"',  # last background pid — shell-set
            '\tbash -lc "echo $$#"',  # arg count — shell-set
            '\tbash -lc "echo $${1}"',  # braced positional — same as $$1
        ],
    )
    def test_safe_patterns_not_flagged(self, line: str) -> None:
        assert mod._is_offender(line) is False


class TestJoinContinuations:
    """Multi-line recipes ending in `\\` get joined before scanning."""

    def test_no_continuation_returns_unchanged(self) -> None:
        assert mod._join_continuations(["a", "b", "c"]) == [
            (1, "a"),
            (2, "b"),
            (3, "c"),
        ]

    def test_single_continuation_joins(self) -> None:
        assert mod._join_continuations(["echo \\", "    $$VAR"]) == [
            (1, "echo     $$VAR")
        ]

    def test_multi_continuation_chain(self) -> None:
        assert mod._join_continuations(["a \\", "b \\", "c"]) == [(1, "a b c")]

    def test_continuation_followed_by_normal_line(self) -> None:
        assert mod._join_continuations(["a \\", "b", "c"]) == [(1, "a b"), (3, "c")]

    def test_trailing_continuation_at_eof_is_preserved(self) -> None:
        # Pathological: file ends with `\` and there's no next line to join.
        # Conservative behavior: keep the literal slash rather than dropping it.
        # (Doesn't affect offender detection — neither form matches the pattern.)
        assert mod._join_continuations(["a \\"]) == [(1, "a \\")]


class TestEndToEnd:
    """Run main() against synthetic Makefiles in tmp_path."""

    def test_clean_makefile_exits_0(self, tmp_path: Path) -> None:
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        assert mod.main(makefile=makefile) == 0

    def test_offending_makefile_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        makefile = tmp_path / "Makefile"
        makefile.write_text('foo:\n\tbash -lc "echo $$VAR"\n', encoding="utf-8")
        assert mod.main(makefile=makefile) == 1
        err = capsys.readouterr().err
        assert "check-makefile-bash-quoting" in err
        assert "Makefile:2" in err  # offender on line 2

    def test_opt_out_marker_suppresses(self, tmp_path: Path) -> None:
        makefile = tmp_path / "Makefile"
        makefile.write_text(
            'foo:\n\tbash -lc "echo $$VAR"  # noqa: bash-lc-quoting\n',
            encoding="utf-8",
        )
        assert mod.main(makefile=makefile) == 0

    def test_multi_line_offender_caught(self, tmp_path: Path) -> None:
        # The opener and the offending $$VAR are on different physical lines;
        # the line-continuation join must catch this.
        makefile = tmp_path / "Makefile"
        makefile.write_text(
            'foo:\n\tbash -lc "echo \\\n\t    $$VAR"\n',
            encoding="utf-8",
        )
        assert mod.main(makefile=makefile) == 1

    def test_missing_makefile_exits_0(self, tmp_path: Path) -> None:
        # A repo without a Makefile (e.g. freshly cloned consumer) is fine.
        absent = tmp_path / "no-such-Makefile"
        assert mod.main(makefile=absent) == 0

    def test_unreadable_makefile_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # A directory at the Makefile path makes `read_text` raise
        # IsADirectoryError (subclass of OSError). Mirrors
        # check_doc_drift's fail-closed exit-2 contract for "scan
        # incomplete". Broken symlinks also exit 2 — see
        # `TestScanOnePathTypes::test_broken_symlink_fails_closed`.
        # (tooling#471 corrected the prior `exists()` early-return
        # that treated broken symlinks as absent.)
        path = tmp_path / "Makefile"
        path.mkdir()
        assert mod.main(makefile=path) == 2
        err = capsys.readouterr().err
        assert "could not read" in err
        assert "Scan is incomplete" in err

    def test_invalid_utf8_does_not_raise(self, tmp_path: Path) -> None:
        # `errors="replace"` should let main() complete on a file with
        # invalid utf-8 bytes (e.g. a binary blob accidentally renamed
        # to Makefile). Replaced bytes become U+FFFD; the scan continues
        # and returns 0 since no offender pattern is present.
        makefile = tmp_path / "Makefile"
        makefile.write_bytes(b"foo:\n\techo \xff\xfe\xfd hello\n")
        assert mod.main(makefile=makefile) == 0

    def test_recipe_line_must_start_with_tab(self, tmp_path: Path) -> None:
        # A pseudo-recipe with leading spaces (not a real recipe) shouldn't fire.
        makefile = tmp_path / "Makefile"
        makefile.write_text('foo:\n    bash -lc "echo $$VAR"\n', encoding="utf-8")
        assert mod.main(makefile=makefile) == 0

    def test_real_repo_makefile_is_clean(self) -> None:
        """The real Makefile in this repo must not have offenders.

        Regression guard for PR #424: if someone reverts the fix in
        `pr-body-drift-check` (or introduces a new offender), this test
        fails immediately.
        """
        assert mod.main() == 0, (
            "Real repo Makefile has offenders. Likely cause: PR #424's "
            "single-quote fix on pr-body-drift-check got reverted, or a "
            "new recipe with the dangerous pattern was added."
        )


class TestMakefileLocal:
    """`Makefile.local` (sibling, consumer-owned, loaded via
    `-include Makefile.local`) must also be scanned so unsafe recipes
    added there can't bypass the gate. See issue #448.
    """

    def test_offending_makefile_local_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Clean primary Makefile + offending Makefile.local → exit 1
        # with the offender attributed to Makefile.local.
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        local = tmp_path / "Makefile.local"
        local.write_text('bar:\n\tbash -lc "echo $$VAR"\n', encoding="utf-8")
        assert mod.main(makefile=makefile) == 1
        err = capsys.readouterr().err
        assert "Makefile.local:2" in err

    def test_missing_makefile_local_is_fine(self, tmp_path: Path) -> None:
        # Primary Makefile clean + no Makefile.local → exit 0. Absence
        # is normal (most consumers have no Makefile.local).
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        assert mod.main(makefile=makefile) == 0

    def test_opt_out_in_makefile_local_suppresses(self, tmp_path: Path) -> None:
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        local = tmp_path / "Makefile.local"
        local.write_text(
            'bar:\n\tbash -lc "echo $$VAR"  # noqa: bash-lc-quoting\n',
            encoding="utf-8",
        )
        assert mod.main(makefile=makefile) == 0

    def test_multi_line_offender_in_makefile_local_caught(self, tmp_path: Path) -> None:
        # Line-continuation join must apply to Makefile.local too.
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        local = tmp_path / "Makefile.local"
        local.write_text(
            'bar:\n\tbash -lc "echo \\\n\t    $$VAR"\n',
            encoding="utf-8",
        )
        assert mod.main(makefile=makefile) == 1

    def test_offenders_in_both_files_reported_together(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Both files have offenders → exit 1, both attributed by basename.
        makefile = tmp_path / "Makefile"
        makefile.write_text('foo:\n\tbash -lc "echo $$A"\n', encoding="utf-8")
        local = tmp_path / "Makefile.local"
        local.write_text('bar:\n\tbash -lc "echo $$B"\n', encoding="utf-8")
        assert mod.main(makefile=makefile) == 1
        err = capsys.readouterr().err
        assert "Makefile:2" in err
        assert "Makefile.local:2" in err
        assert "2 recipe(s)" in err

    def test_unreadable_makefile_local_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Mirrors the primary-Makefile fail-closed contract: an
        # unreadable Makefile.local must also surface exit 2 rather
        # than silently skipping it.
        makefile = tmp_path / "Makefile"
        makefile.write_text("foo:\n\techo hello\n", encoding="utf-8")
        local = tmp_path / "Makefile.local"
        local.mkdir()
        assert mod.main(makefile=makefile) == 2
        err = capsys.readouterr().err
        assert "could not read" in err
        assert "Makefile.local" in err


class TestScanOnePathTypes:
    """`_scan_one(path)` is called for both the primary `Makefile` and
    the sibling `Makefile.local`; its handling of unusual path types
    (broken symlinks, absent files) applies to either. Kept separate
    from `TestMakefileLocal` so the intent — exercising `_scan_one`
    semantics independent of filename — is clear. (tooling#471 round 2.)
    """

    def test_broken_symlink_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # PR #400 review (tooling#471): `_scan_one` returned 0 (clean)
        # for broken symlinks because `path.exists()` follows symlinks
        # and returns False. The comment promised OSError → exit 2.
        # Now the implementation uses `Path.lstat()` first, so broken
        # symlinks are treated as present and then fail closed on read.
        broken = tmp_path / "Makefile"
        broken.symlink_to(tmp_path / "no-such-target")
        status, offenders = mod._scan_one(broken)
        assert status == 2, (
            f"expected exit 2 for broken symlink, got {status} (offenders={offenders})"
        )
        err = capsys.readouterr().err
        assert "could not read" in err
        assert "Scan is incomplete" in err

    def test_absent_path_still_returns_clean(self, tmp_path: Path) -> None:
        # Sanity check: the symlink guard didn't accidentally make
        # plain-absent paths fail. A path that simply doesn't exist
        # must still be treated as clean / absent (status 0).
        # (tooling#471.)
        absent = tmp_path / "no-such-file"  # never created
        status, offenders = mod._scan_one(absent)
        assert status == 0
        assert offenders == []

    def test_present_but_unreadable_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # tooling#471 round 5 review: `path.exists()` returns False on
        # ANY `os.stat` OSError (notably permission denied), which
        # would have classified an unreadable-but-present Makefile as
        # "absent / clean" instead of the documented fail-closed exit
        # 2. The lstat-based check distinguishes FileNotFoundError
        # (truly absent → 0) from other OSError (unreadable → 2).
        #
        # Simulate permission-denied via monkeypatch on
        # `Path.lstat`. (Real chmod 000 doesn't reliably reproduce in
        # CI: euid=root containers ignore mode bits, and parent-dir
        # traversal vs file-read have different code paths.)
        target = tmp_path / "Makefile"
        target.write_text("foo:\n\techo hello\n", encoding="utf-8")
        real_lstat = Path.lstat

        def fake_lstat(self: Path) -> object:
            if self == target:
                raise PermissionError(13, "Permission denied", str(self))
            return real_lstat(self)

        monkeypatch.setattr(Path, "lstat", fake_lstat)
        status, offenders = mod._scan_one(target)
        assert status == 2, (
            f"expected exit 2 for permission-denied lstat, got {status} "
            f"(offenders={offenders})"
        )
        err = capsys.readouterr().err
        assert "could not stat" in err
        assert "PermissionError" in err
        assert "Scan is incomplete" in err
