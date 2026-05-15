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
  - Detects `gh` subprocess invocations (Python: a string list whose
    first item is `"gh"`; shell: `gh ` at start of a line or after
    `&&` / `;`).
  - For each file with a `gh` call, verifies it also contains one
    of the recognized preflight markers:

        gh auth status
        _gh_preflight(

  - Per-line opt-out via `# noqa: gh-preflight` (Python) or
    `# noqa: gh-preflight` (shell) for the rare case where calling
    `gh` without preflight is intentional.

Exit codes: `0` clean, `1` offenders found, `2` scan incomplete (one
or more files could not be read). `2` dominates `1` so callers don't
treat a partial scan as authoritative — same contract as
`check_doc_drift.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# A file is "preflight-clean" if any of these patterns matches.
# Three forms are accepted:
#
#   1. Shell-style literal `gh auth status` (e.g. in a .sh script).
#   2. Python `subprocess.run(["gh", "auth", "status"])` — the list-
#      argument form is the dominant shape in our scripts/.
#   3. A `_gh_preflight(` helper call (the canonical Python factoring
#      used by check_pr_body_drift.py and the issue #378 follow-up
#      will use across the 5 violators).
#
# Each pattern is a `re.Pattern` because the Python list-call form
# tolerates whitespace and quote-style variations that plain substring
# matching can't capture without false positives.
_PREFLIGHT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgh\s+auth\s+status\b"),
    re.compile(r'["\']gh["\']\s*,\s*["\']auth["\']\s*,\s*["\']status["\']'),
    re.compile(r"\b_gh_preflight\s*\("),
)

# Match a `gh` subprocess invocation. The two language-flavored
# regexes are conservative — false negatives (missed gh calls) are
# worse than false positives, so they require a clear shape.
_PY_GH_RE = re.compile(
    r'["\']gh["\']\s*,'  # "gh", or 'gh', inside a list argument
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

_SCAN_ROOT = REPO_ROOT / "scripts"
# Skip this script itself — it contains literal "gh" strings as
# part of the deny-detection patterns above and would self-trigger.
_SKIP_NAMES: frozenset[str] = frozenset({"check_gh_preflight.py"})


def _file_has_gh_call(path: Path, text: str) -> bool:
    """Return True if `text` contains a `gh` subprocess invocation
    that isn't on an opt-out line. Python and shell flavors handled
    separately so we don't grep regex source / docstrings as gh calls.
    """
    if path.suffix == ".py":
        pattern = _PY_GH_RE
    elif path.suffix == ".sh":
        pattern = _SH_GH_RE
    else:
        return False
    for line in text.splitlines():
        if _OPT_OUT in line:
            continue
        if pattern.search(line):
            return True
    return False


def _file_has_preflight(text: str) -> bool:
    """Return True if any preflight pattern matches in `text`."""
    return any(pattern.search(text) for pattern in _PREFLIGHT_PATTERNS)


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
        if _file_has_gh_call(path, text) and not _file_has_preflight(text):
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
