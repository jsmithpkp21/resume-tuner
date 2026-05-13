#!/usr/bin/env python3
"""Run the doc-drift deny-list against the active PR body.

PR #368 review caught a case the source-code-only scanner misses:
the PR description claimed `tests/` was scanned, but a mid-PR commit
had dropped `tests/` from `_SCAN_ROOTS`. The PR body was stale.
This script wraps `gh pr view --json body` and runs the same
deny-list regex against the description.

Usage:

    scripts/check_pr_body_drift.py [PR_NUMBER]

If `PR_NUMBER` is omitted, the script asks `gh` for the PR associated
with the current branch. Same exit-code semantics as
`check_doc_drift.py`: 0 = clean, 1 = drift found.

The deny-list is imported from `check_doc_drift` so the two checks
stay in lockstep — never two lists to maintain.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DRIFT_SCRIPT = _REPO_ROOT / "scripts" / "check_doc_drift.py"


def _load_deny_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Import `_DENY_PATTERNS` from check_doc_drift without mutating
    sys.path. Same loader pattern as the tests."""
    spec = importlib.util.spec_from_file_location("check_doc_drift", _DRIFT_SCRIPT)
    if spec is None or spec.loader is None:
        sys.stderr.write(
            f"check-pr-body-drift: cannot load deny-list from {_DRIFT_SCRIPT}\n"
        )
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # _DENY_PATTERNS is a list[tuple[re.Pattern[str], str]] in the
    # source script; the module-loader returns it as `Any` though,
    # so explicit cast keeps mypy happy.
    patterns: list[tuple[re.Pattern[str], str]] = list(mod._DENY_PATTERNS)
    return patterns


def _fetch_pr_body(pr_number: str | None) -> str:
    """Return the body of `pr_number` (or the current-branch PR if
    omitted). Uses `gh` so the user's auth context is honored."""
    cmd = ["gh", "pr", "view"]
    if pr_number is not None:
        cmd.append(pr_number)
    cmd += ["--json", "body,number"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stderr.write("check-pr-body-drift: `gh pr view` failed:\n" + proc.stderr)
        sys.exit(2)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        sys.stderr.write(
            f"check-pr-body-drift: cannot parse `gh pr view` output: {e}\n"
        )
        sys.exit(2)
    return str(data.get("body") or "")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    pr_number = args[0] if args else None
    body = _fetch_pr_body(pr_number)
    if not body.strip():
        # Empty body → nothing to scan. Treat as clean rather than
        # error — some PRs (especially auto-generated ones) ship with
        # blank descriptions.
        return 0

    patterns = _load_deny_patterns()
    # noqa marker honored same as the source-code scan.
    _OPT_OUT = "noqa: doc-drift"

    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if _OPT_OUT in line:
            continue
        for pattern, hint in patterns:
            m = pattern.search(line)
            if m:
                hits.append((lineno, m.group(0), hint))

    if not hits:
        return 0

    sys.stderr.write(
        f"check-pr-body-drift: {len(hits)} stale API reference(s) in PR body:\n\n"
    )
    for lineno, matched, hint in hits:
        sys.stderr.write(f"  body line {lineno}: `{matched}` — {hint}\n")
    sys.stderr.write(
        f"\nFix via `gh pr edit --body ...` (or the PR UI) before re-requesting "
        f"review. Add `{_OPT_OUT}` to a line if the reference is intentional.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
