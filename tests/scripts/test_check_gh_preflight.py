"""Tests for `scripts/check_gh_preflight.py`.

Strategy: load the script via `importlib.util` (no `sys.path`
mutation) so we can exercise `_file_has_gh_call` and
`_file_has_preflight` as pure functions. The `main()` end-to-end is
covered by writing synthetic scripts under a tmp tree and pointing
the script at it via subprocess invocation.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_gh_preflight.py"
_spec = importlib.util.spec_from_file_location("check_gh_preflight", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_gh_preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_gh_preflight)


class TestFileHasGhCallPython:
    """The Python regex matches `"gh"` or `'gh'` followed by a comma
    inside a list argument. Conservative on purpose — false negatives
    are worse than false positives for a quality gate."""

    def test_subprocess_run_list_call(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text(
            'import subprocess\nsubprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_single_quotes_also_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text("subprocess.run(['gh', 'auth'])\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_no_gh_call_returns_false(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text('print("hello")\n', encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_opt_out_line_skipped(self, tmp_path: Path) -> None:
        # The gh call exists but is intentionally opted out; the
        # detector should NOT count it.
        path = tmp_path / "x.py"
        path.write_text(
            'subprocess.run(["gh", "pr", "view"])  # noqa: gh-preflight\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_string_literal_mention_not_caught(self, tmp_path: Path) -> None:
        # `"gh"` inside a docstring / comment shouldn't trip — but the
        # current regex IS string-literal-based, so a bare `"gh",` in
        # a docstring would. That's intentional false-positive territory
        # (use the opt-out marker). Document the behavior here so a
        # future refactor doesn't accidentally silence real catches.
        path = tmp_path / "x.py"
        # No comma after "gh" → not matched (regex requires the comma).
        path.write_text('msg = "gh is awesome"\n', encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False


class TestFileHasGhCallShell:
    """Shell regex requires `gh ` at command-position (start of line
    or after `;` / `&&` / `|`)."""

    def test_start_of_line_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("gh pr view 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_after_double_amp_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("cd repo && gh pr view 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_comment_form_not_caught(self, tmp_path: Path) -> None:
        # `# gh` in a comment shouldn't fire — start-of-line is `#`.
        path = tmp_path / "x.sh"
        path.write_text("# gh is awesome\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False


class TestFileHasPreflight:
    """Either the `gh auth status` literal OR `_gh_preflight(` counts."""

    def test_inline_gh_auth_status(self) -> None:
        text = '... subprocess.run(["gh", "auth", "status"]) ...'
        assert check_gh_preflight._file_has_preflight(text) is True

    def test_helper_call(self) -> None:
        text = "def main(): _gh_preflight()\n"
        assert check_gh_preflight._file_has_preflight(text) is True

    def test_neither_present(self) -> None:
        text = 'subprocess.run(["gh", "pr", "view"])\n'
        assert check_gh_preflight._file_has_preflight(text) is False


def _run_check_in(repo_root: Path) -> subprocess.CompletedProcess[str]:
    """Copy check_gh_preflight.py into `repo_root/scripts/` and run
    it, so the script's `REPO_ROOT = parents[1]` resolution lands on
    the temp tree. Same pattern as test_check_doc_drift."""
    temp_script = repo_root / "scripts" / "check_gh_preflight.py"
    temp_script.parent.mkdir(parents=True, exist_ok=True)
    temp_script.write_text(_SCRIPT_PATH.read_text(), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(temp_script)],
        capture_output=True,
        text=True,
        check=False,
    )


class TestEndToEnd:
    def test_no_scripts_dir_exits_zero(self, tmp_path: Path) -> None:
        # Empty tree (the script copies itself into scripts/), so no
        # OTHER scripts to scan. Exit 0.
        result = _run_check_in(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_gh_without_preflight_exits_one(self, tmp_path: Path) -> None:
        offender = tmp_path / "scripts" / "bad.py"
        offender.parent.mkdir(parents=True, exist_ok=True)
        offender.write_text(
            'import subprocess\nsubprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        result = _run_check_in(tmp_path)
        assert result.returncode == 1
        assert "bad.py" in result.stderr
        assert "without a `gh auth status` preflight" in result.stderr

    def test_gh_with_preflight_exits_zero(self, tmp_path: Path) -> None:
        good = tmp_path / "scripts" / "good.py"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text(
            "import subprocess\n"
            'subprocess.run(["gh", "auth", "status"])\n'
            'subprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        result = _run_check_in(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_opt_out_marker_silences_offender(self, tmp_path: Path) -> None:
        opted_out = tmp_path / "scripts" / "deliberate.py"
        opted_out.parent.mkdir(parents=True, exist_ok=True)
        opted_out.write_text(
            "import subprocess\n"
            'subprocess.run(["gh", "pr", "view"])  # noqa: gh-preflight\n',
            encoding="utf-8",
        )
        result = _run_check_in(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_script_skips_self(self, tmp_path: Path) -> None:
        # The script's own file (which contains `"gh"` literals in the
        # detection regex source) must not be reported as an offender.
        # _run_check_in always copies the script into scripts/; that
        # copy should be silently skipped.
        result = _run_check_in(tmp_path)
        assert "check_gh_preflight.py" not in result.stderr


@pytest.mark.parametrize(
    "good_form",
    [
        "_gh_preflight()",
        'subprocess.run(["gh", "auth", "status"])',
    ],
)
def test_both_preflight_forms_count_as_clean(tmp_path: Path, good_form: str) -> None:
    """Either calling a helper or doing the gh-auth-status check
    inline satisfies the gate."""
    script = tmp_path / "scripts" / "x.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f"import subprocess\n{good_form}\nsubprocess.run(['gh', 'pr', 'view'])\n",
        encoding="utf-8",
    )
    result = _run_check_in(tmp_path)
    assert result.returncode == 0, result.stderr
