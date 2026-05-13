"""Tests for `scripts/check_no_type_ignore.py`.

Strategy: initialize a temp git repo, stage synthetic Python changes,
invoke the script with cwd set to the temp repo, and assert on exit
code + stderr formatting. We test the staged-diff parser end-to-end
rather than poking at internals — the diff-parsing logic is the
risky part.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_no_type_ignore.py"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `git ARGS...` inside `repo`, raising on nonzero exit."""
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Bare-bones git repo with an initial commit so `--cached` has
    a baseline to diff against."""
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    # Initial commit so HEAD exists.
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "seed")
    return tmp_path


def _run_check(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


class TestExitZeroPaths:
    def test_empty_staging_area_exits_zero(self, repo: Path) -> None:
        # Nothing staged at all.
        result = _run_check(repo)
        assert result.returncode == 0, result.stderr

    def test_staged_python_without_type_ignore_exits_zero(self, repo: Path) -> None:
        src = repo / "src" / "ok.py"
        src.parent.mkdir(parents=True)
        src.write_text("x: int = 1\n", encoding="utf-8")
        _git(repo, "add", "src/ok.py")
        result = _run_check(repo)
        assert result.returncode == 0, result.stderr

    def test_staged_non_python_with_type_ignore_string_exits_zero(
        self, repo: Path
    ) -> None:
        # YAML / TOML / etc. files happen to contain the literal
        # string but aren't Python — pathspec filters them out.
        src = repo / "notes.md"
        src.write_text("Sometimes I add `# type: ignore` in code.\n", encoding="utf-8")
        _git(repo, "add", "notes.md")
        result = _run_check(repo)
        assert result.returncode == 0, result.stderr


class TestExitNonzeroPaths:
    def test_staged_new_type_ignore_in_root_python_blocks(self, repo: Path) -> None:
        src = repo / "foo.py"
        src.write_text('bad: int = "x"  # type: ignore\n', encoding="utf-8")
        _git(repo, "add", "foo.py")
        result = _run_check(repo)
        assert result.returncode == 1
        assert "foo.py" in result.stderr
        assert "type: ignore" in result.stderr

    def test_staged_new_type_ignore_in_nested_python_blocks(self, repo: Path) -> None:
        # Catches the pathspec bug that was Copilot's #1 comment —
        # `*.py` only matched root files; we need src/foo.py to
        # also be scanned.
        src = repo / "src" / "deep" / "nested.py"
        src.parent.mkdir(parents=True)
        src.write_text("y = 1  # type: ignore[assignment]\n", encoding="utf-8")
        _git(repo, "add", "src/deep/nested.py")
        result = _run_check(repo)
        assert result.returncode == 1, result.stderr
        assert "src/deep/nested.py" in result.stderr

    def test_reports_correct_line_number(self, repo: Path) -> None:
        src = repo / "with_lines.py"
        src.write_text(
            "# line 1\n# line 2\n# line 3\nbad = 1  # type: ignore\n# line 5\n",
            encoding="utf-8",
        )
        _git(repo, "add", "with_lines.py")
        result = _run_check(repo)
        assert result.returncode == 1
        # The reported line is the file's line 4.
        assert "with_lines.py:4" in result.stderr

    def test_multiple_hits_all_reported(self, repo: Path) -> None:
        src = repo / "multi.py"
        src.write_text(
            "a = 1  # type: ignore\nb = 2  # type: ignore[assignment]\n",
            encoding="utf-8",
        )
        _git(repo, "add", "multi.py")
        result = _run_check(repo)
        assert result.returncode == 1
        # Header says "2 new" and both lines appear in the output.
        assert "2 new" in result.stderr
        assert "multi.py:1" in result.stderr
        assert "multi.py:2" in result.stderr


class TestUnstagedNotConsidered:
    """The check intentionally scans the staging area, not the working
    tree. An unstaged `# type: ignore` shouldn't trip it."""

    def test_unstaged_change_does_not_block(self, repo: Path) -> None:
        src = repo / "wt.py"
        src.write_text("z = 0  # type: ignore\n", encoding="utf-8")
        # Note: NOT calling `git add` — unstaged.
        result = _run_check(repo)
        assert result.returncode == 0, result.stderr
