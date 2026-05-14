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

Exits 0 if every gh-using script has a preflight, 1 otherwise.
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
# Shell: `gh ` after a command-start position. `^gh\b` covers start of
# line; `[;&|]\s*gh\b` covers chained commands. Skip `# ... gh ...`
# comments and string literals (the script body should grep cleanly).
_SH_GH_RE = re.compile(r"(?:^|[;&|]\s*)gh\s+\w")

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
    for path in sorted(_SCAN_ROOT.iterdir()):
        if not path.is_file():
            continue
        if path.name in _SKIP_NAMES:
            continue
        if path.suffix not in {".py", ".sh"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # Best-effort surfacing — same posture as check_doc_drift.
            # Report as offender so the user knows we couldn't verify.
            offenders.append(path)
            continue
        if _file_has_gh_call(path, text) and not _file_has_preflight(text):
            offenders.append(path)

    if not offenders:
        return 0

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
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
