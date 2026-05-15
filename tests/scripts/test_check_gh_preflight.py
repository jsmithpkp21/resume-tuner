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
    """AST scan: any list/tuple literal whose first element is the
    string `"gh"` counts as a `gh` subprocess invocation. Catches
    both inline `subprocess.run(["gh", ...])` and the indirect
    `cmd = ["gh", ...]; subprocess.run(cmd)`. Mentions inside
    docstrings or comments parse as `Constant`, not `List`, so they
    don't trigger (issue #447)."""

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

    def test_opt_out_on_call_line_of_multiline_list(self, tmp_path: Path) -> None:
        # PR #400 review (tooling#471): pre-fix, the opt-out check was
        # tied to the FIRST STRING LITERAL's lineno. After black/ruff
        # reformats a long call across multiple lines, the marker
        # naturally lives on the `subprocess.run(` line, not on the
        # `"gh",` line — and was silently missed. The fix uses the
        # enclosing-statement range so the marker is recognized
        # anywhere in `[start_lineno, end_lineno]`.
        path = tmp_path / "x.py"
        path.write_text(
            "import subprocess\n"
            "subprocess.run(  # noqa: gh-preflight\n"
            "    [\n"
            '        "gh",\n'
            '        "pr",\n'
            '        "view",\n'
            "    ]\n"
            ")\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_opt_out_on_closing_bracket_of_multiline_list(self, tmp_path: Path) -> None:
        # Same fix, opt-out on the closing-bracket line at the end of
        # the call. Both placements are common after auto-format.
        path = tmp_path / "x.py"
        path.write_text(
            "import subprocess\n"
            "subprocess.run(\n"
            "    [\n"
            '        "gh",\n'
            '        "pr",\n'
            '        "view",\n'
            "    ]\n"
            ")  # noqa: gh-preflight\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_opt_out_on_unrelated_line_does_not_silence(self, tmp_path: Path) -> None:
        # Sanity: the range-based check is bounded to the enclosing
        # statement. A `# noqa: gh-preflight` on a totally unrelated
        # earlier line shouldn't silence the gh call.
        path = tmp_path / "x.py"
        path.write_text(
            "import subprocess\n"
            "x = 1  # noqa: gh-preflight\n"
            'subprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_string_literal_mention_not_caught(self, tmp_path: Path) -> None:
        # AST-based detection: `"gh"` inside a string literal parses as
        # a `Constant`, not a `List`, so it's not matched. This is the
        # issue #447 false-positive fix.
        path = tmp_path / "x.py"
        path.write_text('msg = "gh is awesome"\n', encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_docstring_with_subprocess_example_not_caught(self, tmp_path: Path) -> None:
        # Issue #447: a docstring containing the literal text of a
        # subprocess call must NOT be treated as a real call.
        path = tmp_path / "x.py"
        path.write_text(
            '"""Example: subprocess.run(["gh", "pr", "view"])"""\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_indirect_list_assignment_caught(self, tmp_path: Path) -> None:
        # `cmd = ["gh", ...]; subprocess.run(cmd)` — the AST scan walks
        # every List/Tuple, so the indirection through a variable
        # doesn't cause a false negative.
        path = tmp_path / "x.py"
        path.write_text(
            'cmd = ["gh", "pr", "view"]\nimport subprocess\nsubprocess.run(cmd)\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_syntax_error_returns_false(self, tmp_path: Path) -> None:
        # A file with invalid Python can't actually run gh calls;
        # other gates (ruff, py_compile) will surface the syntax
        # error. AST scan returns False (no gh calls detected).
        path = tmp_path / "x.py"
        path.write_text("def broken(\n    return 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False


class TestFileHasGhCallShell:
    """Shell regex matches `gh ` at any command-invocation position:
    start of line (possibly indented), after `;` / `&&` / `|`, after
    `$(` (POSIX command substitution), after backtick (legacy
    substitution), or after `(` (subshell)."""

    def test_start_of_line_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("gh pr view 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_after_double_amp_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("cd repo && gh pr view 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_command_substitution_caught(self, tmp_path: Path) -> None:
        # `$(gh ...)` — the original PR #412 round-3 false negative.
        # scripts/create_branch.sh in tooling uses exactly this shape
        # for `ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --json title,labels)`.
        path = tmp_path / "x.sh"
        path.write_text("OUT=$(gh issue view 123 --json title)\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_backtick_substitution_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("OUT=`gh pr view 1`\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_subshell_caught(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("(gh pr view 1 > out.txt)\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_indented_caught(self, tmp_path: Path) -> None:
        # A continuation line indented after `\` would otherwise be
        # missed by a strict `^gh` anchor.
        path = tmp_path / "x.sh"
        path.write_text("    gh pr view 1\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is True

    def test_comment_form_not_caught(self, tmp_path: Path) -> None:
        # `# gh` in a comment shouldn't fire — `#` is not in any
        # command-prefix alternation.
        path = tmp_path / "x.sh"
        path.write_text("# gh is awesome\n", encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False

    def test_string_literal_form_not_caught(self, tmp_path: Path) -> None:
        # `echo "gh foo"` — gh inside a string literal shouldn't fire.
        # The regex requires `gh\s+\w` (whitespace + word char), and
        # `gh` here is followed by ` foo"` — `\w` matches `f`, so this
        # would match unless `"` blocks the prefix. The prefix `"` is
        # not in any alternation, so this stays clean.
        path = tmp_path / "x.sh"
        path.write_text('echo "gh foo bar"\n', encoding="utf-8")
        assert check_gh_preflight._file_has_gh_call(path, path.read_text()) is False


class TestFileHasPreflightPython:
    """AST scan: a real `subprocess.run(["gh", "auth", "status"])`
    list/tuple OR a `Call` to `_gh_preflight` counts. Mentions inside
    docstrings or comments do NOT count (issue #447)."""

    def test_inline_gh_auth_status(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text(
            'import subprocess\nsubprocess.run(["gh", "auth", "status"])\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_helper_call(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text("def main():\n    _gh_preflight()\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_helper_call_via_attribute(self, tmp_path: Path) -> None:
        # `mod._gh_preflight()` — Attribute access form.
        path = tmp_path / "x.py"
        path.write_text("import helpers\nhelpers._gh_preflight()\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_neither_present(self, tmp_path: Path) -> None:
        path = tmp_path / "x.py"
        path.write_text('subprocess.run(["gh", "pr", "view"])\n', encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_docstring_mention_does_not_count(self, tmp_path: Path) -> None:
        # Issue #447 core case: a script mentions `gh auth status` in
        # its docstring but never calls it. Must NOT be treated as
        # preflight-satisfied.
        path = tmp_path / "x.py"
        path.write_text(
            '"""Remember to run gh auth status before invoking gh."""\n'
            'import subprocess\nsubprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_string_literal_does_not_count(self, tmp_path: Path) -> None:
        # The literal text of a subprocess call inside a string
        # (e.g. example code in a docstring) must NOT satisfy.
        path = tmp_path / "x.py"
        path.write_text(
            'msg = \'subprocess.run(["gh", "auth", "status"])\'\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False


class TestFileHasPreflightShell:
    """Shell preflight matches `gh auth status` only at a command-
    prefix position so comments / strings don't satisfy."""

    def test_real_invocation_counts(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("gh auth status\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_chained_invocation_counts(self, tmp_path: Path) -> None:
        path = tmp_path / "x.sh"
        path.write_text("cd repo && gh auth status\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_comment_mention_does_not_count(self, tmp_path: Path) -> None:
        # `# gh auth status` in a comment shouldn't satisfy the gate.
        path = tmp_path / "x.sh"
        path.write_text("# Remember: gh auth status before gh\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_inline_comment_after_invocation_strips_correctly(
        self, tmp_path: Path
    ) -> None:
        # Trailing comment after a real `gh auth status` line: the
        # invocation comes before the `#` so it must still count.
        path = tmp_path / "x.sh"
        path.write_text("gh auth status  # preflight\n", encoding="utf-8")
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_if_not_negation_idiom_counts(self, tmp_path: Path) -> None:
        # Regression guard: scripts/create_pr_epic.sh uses
        # `if ! gh auth status >/dev/null 2>&1; then` as its preflight.
        # Must still be recognized as a real invocation.
        path = tmp_path / "x.sh"
        path.write_text(
            "if ! gh auth status >/dev/null 2>&1; then\n"
            '    echo "not authenticated" >&2\n'
            "    exit 1\n"
            "fi\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_quoted_string_mention_does_not_count(self, tmp_path: Path) -> None:
        # PR #148 review (tooling#471): pre-fix `_SH_PREFLIGHT_RE` was
        # `\bgh\s+auth\s+status\b` — matched ANYWHERE in the line
        # including inside echo string arguments. `echo "run gh auth
        # status"` could satisfy the gate without a real call. Now the
        # regex requires command-prefix anchoring.
        path = tmp_path / "x.sh"
        path.write_text(
            '#!/usr/bin/env bash\necho "run gh auth status"\ngh pr view\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_echo_argument_with_bang_does_not_count(self, tmp_path: Path) -> None:
        # `echo ! gh auth status` — the `!` is argument text, not
        # shell negation. The `!\s+` anchor must require command-position
        # context, not match anywhere on the line.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\necho ! gh auth status\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_nested_bash_lc_single_quoted_counts(self, tmp_path: Path) -> None:
        # `bash -lc 'gh auth status'` — real nested-shell preflight.
        # `gh` is immediately after the opening single quote; the
        # `bash\s+-[lc]+\s+['"]` anchor catches it.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\nbash -lc 'gh auth status' || exit 2\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_nested_bash_c_double_quoted_counts(self, tmp_path: Path) -> None:
        # Same shape, double-quoted.
        path = tmp_path / "x.sh"
        path.write_text(
            '#!/usr/bin/env bash\nbash -c "gh auth status"\ngh pr view\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_nested_bash_lc_as_string_argument_does_not_count(
        self, tmp_path: Path
    ) -> None:
        # tooling#471 round 2 review: round-1 of the bash-lc anchor didn't
        # require `bash` itself to be at command position. So a string
        # argument like `echo "bash -lc 'gh auth status'"` (where the
        # whole nested-shell text is just argument data to echo)
        # falsely satisfied the gate. Now `bash` must follow the same
        # command-start anchors as direct gh invocations.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\necho \"bash -lc 'gh auth status'\"\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_nested_bash_lc_after_chain_op_counts(self, tmp_path: Path) -> None:
        # Positive control for the anchor: real chained nested-shell
        # invocation. `bash` is after `&&`, which IS a command-start
        # anchor, so the gate is satisfied.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\nsetup && bash -lc 'gh auth status'\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_subshell_in_argument_string_does_not_count(self, tmp_path: Path) -> None:
        # tooling#471 round 3 review: the subshell `\(\s*` anchor was
        # unscoped, so `echo "(gh auth status)"` matched even though
        # `(` is literal text inside an echo argument. Now `(` must
        # itself be at a command-start position (start of line or
        # after a chain op).
        path = tmp_path / "x.sh"
        path.write_text(
            '#!/usr/bin/env bash\necho "(gh auth status)"\ngh pr view\n',
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_subshell_in_single_quoted_argument_does_not_count(
        self, tmp_path: Path
    ) -> None:
        # Same bypass shape, single-quoted.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\necho '(gh auth status)'\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is False

    def test_subshell_at_line_start_counts(self, tmp_path: Path) -> None:
        # Positive control: a real subshell `(gh auth status)` at line
        # start IS a valid invocation. The anchor must still recognize
        # it after the scoping fix.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\n(gh auth status)\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True

    def test_subshell_after_chain_op_counts(self, tmp_path: Path) -> None:
        # Positive control: `setup && (gh auth status)` — subshell
        # immediately after a chain op is also a real call.
        path = tmp_path / "x.sh"
        path.write_text(
            "#!/usr/bin/env bash\nsetup && (gh auth status)\ngh pr view\n",
            encoding="utf-8",
        )
        assert check_gh_preflight._file_has_preflight(path, path.read_text()) is True


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

    def test_unreadable_file_exits_2(self, tmp_path: Path) -> None:
        # A broken symlink (target does not exist) raises OSError on
        # read. Previously the script appended the path to `offenders`
        # and mis-labeled it as "calls gh without preflight" even
        # though we never saw the contents. Now it must be tracked
        # separately and exit 2 ("scan incomplete"), matching
        # check_doc_drift's contract.
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        broken = scripts_dir / "broken.py"
        broken.symlink_to(tmp_path / "does_not_exist.py")
        result = _run_check_in(tmp_path)
        assert result.returncode == 2, result.stderr
        assert "unreadable" in result.stderr
        assert "scripts/broken.py" in result.stderr
        # And critically: NOT mis-labeled as a preflight offender.
        assert "without a `gh auth status` preflight" not in result.stderr

    def test_docstring_mention_does_not_satisfy_preflight(self, tmp_path: Path) -> None:
        # Issue #447 regression guard: a script that mentions
        # `gh auth status` in its docstring but never actually calls
        # it must still be reported as an offender.
        offender = tmp_path / "scripts" / "doc_only.py"
        offender.parent.mkdir(parents=True, exist_ok=True)
        offender.write_text(
            '"""Tool that uses gh.\n\n'
            "Make sure to run gh auth status before invoking this.\n"
            '"""\n'
            'import subprocess\nsubprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        result = _run_check_in(tmp_path)
        assert result.returncode == 1, result.stderr
        assert "doc_only.py" in result.stderr
        assert "without a `gh auth status` preflight" in result.stderr

    def test_unreadable_plus_offender_still_exits_2(self, tmp_path: Path) -> None:
        # Both a real preflight offender and an unreadable file. The
        # offender report should still appear (so the user sees what
        # we did find), but exit code must be 2 (scan incomplete)
        # rather than 1 (offenders found), because the scan was
        # incomplete and the offender list shouldn't be treated as
        # authoritative.
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "bad.py").write_text(
            'import subprocess\nsubprocess.run(["gh", "pr", "view"])\n',
            encoding="utf-8",
        )
        broken = scripts_dir / "broken.py"
        broken.symlink_to(tmp_path / "does_not_exist.py")
        result = _run_check_in(tmp_path)
        assert result.returncode == 2, result.stderr
        # Offender report still surfaced.
        assert "bad.py" in result.stderr
        assert "without a `gh auth status` preflight" in result.stderr
        # Unreadable section also surfaced.
        assert "broken.py" in result.stderr
        assert "unreadable" in result.stderr


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
