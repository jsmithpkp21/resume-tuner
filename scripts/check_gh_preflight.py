#!/usr/bin/env python3
"""Verify scripts that call `gh` also include a `gh auth status` preflight.

AGENTS.md mandates:

  Before using `gh` CLI in any script or make target, add `gh auth
  status` as an explicit preflight with a clear error and remediation
  message. A stale or expired `GITHUB_TOKEN` env var silently overrides
  stored credentials and causes HTTP 401 errors.

PR #373 review surfaced that I'd violated this rule in
`check_pr_body_drift.py` despite the guidance being a turn away in
AGENTS.md. This meta-check catches the regression before review.

How it works:

  - Walks every `.py` and `.sh` file under `scripts/`.
  - Detects `gh` subprocess invocations:
      Python: an AST `List`/`Tuple` node whose first element is the
        string literal `"gh"` (catches both `subprocess.run(["gh", ...])`
        and `cmd = ["gh", ...]; subprocess.run(cmd)`). Mentions of
        `"gh"` inside docstrings / comments parse as a `Constant`
        string rather than a `List`, so they're naturally excluded.
      Shell: `gh ` at a command-prefix position (start of line,
        after `&&` / `;` / `|`, after `$(`, backtick, or `(`).
  - For each file with a `gh` call, verifies it also contains a real
    preflight invocation:
      Python: a `Call` whose function name resolves to
        `_gh_preflight`, OR a `List`/`Tuple` starting with the three
        literals `"gh", "auth", "status"`.
      Shell: a command-prefix-anchored `gh auth status` line.
    Issue #447: previously this was a free-text regex match, so a
    docstring or comment mentioning `gh auth status` would falsely
    satisfy the gate. The AST/anchored approach catches only real
    invocations.
  - Per-line opt-out via `# noqa: gh-preflight` (Python or shell)
    for the rare case where calling `gh` without preflight is
    intentional.

Exit codes: `0` clean, `1` offenders found, `2` scan incomplete (one
or more files could not be read). `2` dominates `1` so callers don't
treat a partial scan as authoritative — same contract as
`check_doc_drift.py`.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Shell `gh auth status` invocation. Used on the *pre-comment* part
# of each line so that `# gh auth status …` in a comment doesn't
# count as a real preflight (issue #447). Permissive about leading
# context so common idioms like `if ! gh auth status; then` and
# `if gh auth status; then` are still recognized.
# Shell preflight regex — command-prefix anchored so a non-executed
# mention like `echo "run gh auth status"` doesn't satisfy the gate.
# Two-branch alternation:
#
#   (A) Direct invocation: `gh auth status` immediately after a
#       command-start anchor (start of line, after `;`/`&`/`|`, inside
#       `$()` / backtick, OR inside a subshell `(` that is ITSELF at
#       a command-start position — `^\s*\(` or `[;&|]\s*\(`. The
#       subshell anchor was unscoped in round 1; round 3 review
#       caught that `echo "(gh auth status)"` bypassed because `(`
#       in argument text would otherwise match).
#   (B) Nested-shell invocation: `bash -lc 'gh auth status'` /
#       `bash -c "gh auth status"`. The `bash -[lc]+ '` opener must
#       ITSELF appear at a command-start position — otherwise
#       `echo "bash -lc 'gh auth status'"` (where the whole nested-
#       shell string is just argument text to echo) would satisfy.
#
# Round 2 review on this PR caught the missing anchor on branch (B).
_SH_PREFLIGHT_RE = re.compile(
    r"""
    (?:
        # Branch (A): direct gh auth status invocation at command position.
        (?:
            ^\s*(?:if\s+)?(?:!\s+)?
            |[;&|]\s*(?:!\s+)?
            |\$\(
            |`
            |(?:^\s*|[;&|]\s*)\(\s*(?:!\s+)?
        )
        gh\s+auth\s+status\b
        |
        # Branch (B): nested-shell preflight. `bash` MUST be at command
        # position (same anchor set as branch A), then `-lc`/`-c`, then
        # an open quote, then gh auth status. (tooling#471 round 2.)
        (?:
            ^\s*(?:if\s+)?(?:!\s+)?
            |[;&|]\s*(?:!\s+)?
            |\$\(
            |`
            |(?:^\s*|[;&|]\s*)\(\s*(?:!\s+)?
        )
        bash\s+-[lc]+\s+['"]gh\s+auth\s+status\b
    )
    """,
    re.VERBOSE,
)

# Shell: `gh ` after a command-start position. The alternation
# enumerates every shape we've seen `gh` invoked in:
#   - `^\s*gh` — start of line (possibly indented after a `\` line
#     continuation).
#   - `[;&|]\s*gh` — chained commands (`;`, `&&`, `||`, `|`).
#   - `\$\(gh` — POSIX command substitution: `X=$(gh ...)`.
#   - `` `gh `` — legacy backtick command substitution.
#   - `\(\s*gh` — subshell or function body.
# This is wider than the original `^|[;&|]` form (added in PR #412
# round-3 review to catch the false negative in scripts/create_branch.sh
# `ISSUE_JSON=$(gh issue view …)`). The trade-off is occasional false
# positives if a comment line happens to contain one of these shapes;
# `# noqa: gh-preflight` opt-out covers that case.
# See tests in tests/scripts/test_check_gh_preflight.py — coverage
# for each alternation branch, with test_indented_caught additionally
# pinning the `\s*` quantifier inside the start-of-line branch (names
# kept unbroken so they're greppable):
#   test_start_of_line_caught
#   test_after_double_amp_caught
#   test_command_substitution_caught
#   test_backtick_substitution_caught
#   test_subshell_caught
#   test_indented_caught
_SH_GH_RE = re.compile(r"(?:^\s*|[;&|]\s*|\$\(|`|\(\s*)gh\s+\w")

_OPT_OUT = "noqa: gh-preflight"


def _python_gh_call_lines(text: str) -> list[tuple[int, int]]:
    """Return `(start_lineno, end_lineno)` ranges for statements that
    contain a list/tuple literal whose first element is the string
    `"gh"`. Catches both the dominant `subprocess.run(["gh", ...])`
    shape and the `cmd = ["gh", ...]` indirection. Mentions of `"gh"`
    inside docstrings / comments are `Constant` nodes, not `List`, so
    they're naturally excluded (issue #447).

    Range-based (not point-based) so the `# noqa: gh-preflight`
    opt-out marker can appear ANYWHERE within the enclosing statement
    — including the `subprocess.run(` line or the closing-bracket
    line of a multi-line list literal. Pre-fix the marker had to land
    on the same line as the first string literal, which was fragile
    after black/ruff reformatted long calls. (tooling#471.)
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # A file with invalid Python can't be running gh calls
        # regardless — fall through and let other gates (ruff, etc.)
        # surface the syntax error.
        return []

    # Build a parent map so we can walk up from a List/Tuple to find
    # the innermost enclosing `ast.stmt` node, whose `lineno` /
    # `end_lineno` give the full statement range.
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    def _innermost_stmt(node: ast.AST) -> ast.stmt | None:
        cur: ast.AST | None = node
        while cur is not None and not isinstance(cur, ast.stmt):
            cur = parents.get(id(cur))
        return cur if isinstance(cur, ast.stmt) else None

    seen_stmts: set[int] = set()
    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
            continue
        first = node.elts[0]
        if not (isinstance(first, ast.Constant) and first.value == "gh"):
            continue
        stmt = _innermost_stmt(node)
        if stmt is None:
            continue
        if id(stmt) in seen_stmts:
            continue
        seen_stmts.add(id(stmt))
        end = getattr(stmt, "end_lineno", None) or stmt.lineno
        ranges.append((stmt.lineno, end))
    return ranges


def _python_has_preflight(text: str) -> bool:
    """True if the AST contains a real preflight: either a list/tuple
    starting with `("gh", "auth", "status", ...)`, or a `Call` node
    invoking a function named `_gh_preflight`. Same docstring-immunity
    as `_python_gh_call_lines` — preflights mentioned in strings or
    comments do NOT count.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id == "_gh_preflight":
                return True
            if isinstance(f, ast.Attribute) and f.attr == "_gh_preflight":
                return True
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) >= 3:
            vals = [
                e.value if isinstance(e, ast.Constant) else None for e in node.elts[:3]
            ]
            if vals == ["gh", "auth", "status"]:
                return True
    return False


_SCAN_ROOT = REPO_ROOT / "scripts"
# Skip this script itself — it contains literal "gh" strings as
# part of the deny-detection patterns above and would self-trigger.
_SKIP_NAMES: frozenset[str] = frozenset({"check_gh_preflight.py"})


def _file_has_gh_call(path: Path, text: str) -> bool:
    """Return True if `text` contains a `gh` subprocess invocation
    that isn't on an opt-out line. Python uses an AST scan so
    docstring / comment mentions don't trigger (issue #447). Shell
    keeps the command-prefix-anchored regex.
    """
    if path.suffix == ".py":
        lines = text.splitlines()
        for start, end in _python_gh_call_lines(text):
            # Opt-out can appear ANYWHERE in the enclosing statement
            # range. (tooling#471 — pre-fix the check was tied to the
            # first-string lineno, missing markers on the `run(` line
            # or closing-bracket line of multi-line list literals.)
            in_range = (
                lines[i - 1] for i in range(start, end + 1) if 0 < i <= len(lines)
            )
            if any(_OPT_OUT in line for line in in_range):
                continue
            return True
        return False
    if path.suffix == ".sh":
        for line in text.splitlines():
            if _OPT_OUT in line:
                continue
            if _SH_GH_RE.search(line):
                return True
        return False
    return False


def _file_has_preflight(path: Path, text: str) -> bool:
    """Return True if the file contains a real preflight (not just a
    text mention). Python uses AST; shell uses a command-prefix-
    anchored regex so a `# gh auth status` comment doesn't count.
    """
    if path.suffix == ".py":
        return _python_has_preflight(text)
    if path.suffix == ".sh":
        for line in text.splitlines():
            # Strip from the first `#` so commented-out mentions
            # (`# gh auth status …` or `echo X  # gh auth status`)
            # don't satisfy. Naive — doesn't track `#` inside strings,
            # but the preflight marker is unlikely to share a line
            # with a literal `#` in a string.
            code = line.split("#", 1)[0]
            if _SH_PREFLIGHT_RE.search(code):
                return True
        return False
    return False


def main() -> int:
    if not _SCAN_ROOT.exists():
        # No scripts/ dir → nothing to check. Treat as clean rather
        # than error so this gate is portable across freshly-cloned
        # consumer repos that haven't built out scripts yet.
        return 0

    offenders: list[Path] = []
    unreadable: list[tuple[Path, OSError]] = []
    # Recursive walk to match the module-docstring promise ("walks
    # every `.py` and `.sh` file under `scripts/`"). Today every
    # consumer's `scripts/` is flat, so this is forward-compat; if a
    # subdir gets added later, the check picks it up without code
    # change.
    for path in sorted(_SCAN_ROOT.rglob("*")):
        # `is_file()` follows symlinks and returns False for a broken
        # one — without `is_symlink()` here we'd skip broken links
        # silently, masking the unreadable-file case we want to
        # fail-closed on. Same posture as check_doc_drift.
        if not (path.is_file() or path.is_symlink()):
            continue
        if path.name in _SKIP_NAMES:
            continue
        if path.suffix not in {".py", ".sh"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # Track separately from offenders — calling an unreadable
            # file a "preflight offender" is wrong (we don't know if
            # it calls `gh` at all) and would mask scan-incompleteness.
            # Mirrors check_doc_drift's fail-closed exit-2 contract.
            # See tests in tests/scripts/test_check_gh_preflight.py:
            # test_unreadable_file_exits_2 (broken-symlink → exit 2,
            # NOT mis-labeled as offender) and
            # test_unreadable_plus_offender_still_exits_2 (mixed case
            # still exits 2 — scan-incomplete wins over offenders).
            unreadable.append((path, exc))
            continue
        if _file_has_gh_call(path, text) and not _file_has_preflight(path, text):
            offenders.append(path)

    if offenders:
        sys.stderr.write(
            f"check-gh-preflight: {len(offenders)} script(s) call `gh` without a "
            "`gh auth status` preflight:\n\n"
        )
        for path in offenders:
            rel = path.relative_to(REPO_ROOT)
            sys.stderr.write(f"  {rel}\n")
        sys.stderr.write(
            "\nAdd a `_gh_preflight()` helper (or inline `gh auth status` check) "
            "before any `gh` subprocess call. See AGENTS.md Execution Guardrails "
            f"or add `# {_OPT_OUT}` per line if the call is intentionally "
            "preflight-free.\n"
        )

    if unreadable:
        sys.stderr.write(
            f"\ncheck-gh-preflight: {len(unreadable)} unreadable file(s) — scan is incomplete:\n\n"
        )
        for path, read_err in unreadable:
            rel = path.relative_to(REPO_ROOT)
            sys.stderr.write(f"  {rel}: {read_err.__class__.__name__}: {read_err}\n")
        sys.stderr.write(
            "\nResolve the read errors above and re-run; results may be incomplete "
            "until every file is scannable.\n"
        )
        return 2

    if offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
