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
`check_doc_drift.py`: 0 = clean, 1 = drift found, 2 = environment /
tooling error (missing `gh`, auth failure, malformed JSON, etc.).

Both the deny-list regex AND the opt-out marker string are imported
from `check_doc_drift` so the two checks stay in lockstep — never
two lists or two strings to maintain.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DRIFT_SCRIPT = _REPO_ROOT / "scripts" / "check_doc_drift.py"


def _load_drift_module() -> ModuleType:
    """Import `check_doc_drift.py` from disk without mutating
    `sys.path`. Both `_DENY_PATTERNS` and `_OPT_OUT_MARKER` come
    from the loaded module so the PR-body check tracks every future
    edit to the source-code check without manual sync.
    """
    spec = importlib.util.spec_from_file_location("check_doc_drift", _DRIFT_SCRIPT)
    if spec is None or spec.loader is None:
        sys.stderr.write(
            f"check-pr-body-drift: cannot load deny-list from {_DRIFT_SCRIPT}\n"
        )
        sys.exit(2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _gh_preflight() -> None:
    """Verify `gh` is installed AND authenticated before any real
    invocation. Matches the AGENTS.md "Before using `gh` CLI in any
    script or make target, add `gh auth status` as an explicit
    preflight" guidance. A stale `GITHUB_TOKEN` env var silently
    overrides stored credentials and causes HTTP 401 — surfacing
    it here is the cheap fix.
    """
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "check-pr-body-drift: `gh` CLI not found on PATH.\n"
            "Install with: https://cli.github.com/  (or your package manager).\n"
        )
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(
            "check-pr-body-drift: `gh auth status` failed; aborting.\n\n"
            f"{proc.stderr}\n"
            "Common causes: not logged in (run `gh auth login`), or a stale\n"
            "GITHUB_TOKEN env var overriding stored credentials.\n"
        )
        sys.exit(2)


def _fetch_pr_body(pr_number: str | None) -> str:
    """Return the body of `pr_number` (or the current-branch PR if
    omitted). Calls `_gh_preflight` first so missing-binary and auth
    failures produce actionable errors rather than tracebacks.
    """
    _gh_preflight()
    cmd = ["gh", "pr", "view"]
    if pr_number is not None:
        cmd.append(pr_number)
    cmd += ["--json", "body,number"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        sys.stderr.write(f"check-pr-body-drift: failed to invoke `gh`: {e}\n")
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(
            "check-pr-body-drift: `gh pr view` failed:\n"
            f"  stdout: {proc.stdout}\n"
            f"  stderr: {proc.stderr}\n"
        )
        sys.exit(2)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        sys.stderr.write(
            f"check-pr-body-drift: cannot parse `gh pr view` output: {e}\n"
        )
        sys.exit(2)
    return str(data.get("body") or "")


def scan_body(body: str) -> list[tuple[int, str, str]]:
    """Run the deny-list against a PR body string; return hits.

    Returned tuple is `(line_number, matched_text, remediation_hint)`.
    Lines containing the opt-out marker (imported from
    `check_doc_drift`) are skipped. Pure function — no I/O, no
    subprocess; the unit tests pass canned strings here.
    """
    mod = _load_drift_module()
    patterns: list[tuple[re.Pattern[str], str]] = list(mod._DENY_PATTERNS)
    opt_out: str = mod._OPT_OUT_MARKER

    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(body.splitlines(), start=1):
        if opt_out in line:
            continue
        for pattern, hint in patterns:
            m = pattern.search(line)
            if m:
                hits.append((lineno, m.group(0), hint))
    return hits


def _format_report(hits: list[tuple[int, str, str]], opt_out: str) -> str:
    """Format the stderr diagnostic. Extracted so the tests can
    assert on the exact output without re-running subprocess."""
    out = [
        f"check-pr-body-drift: {len(hits)} stale API reference(s) in PR body:",
        "",
    ]
    for lineno, matched, hint in hits:
        out.append(f"  body line {lineno}: `{matched}` — {hint}")
    out += [
        "",
        f"Fix via `gh pr edit --body ...` (or the PR UI) before re-requesting "
        f"review. Add `{opt_out}` to a line if the reference is intentional.",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    pr_number = args[0] if args else None
    body = _fetch_pr_body(pr_number)
    if not body.strip():
        # Empty body → nothing to scan. Treat as clean rather than
        # error — some PRs (especially auto-generated ones) ship with
        # blank descriptions.
        return 0

    hits = scan_body(body)
    if not hits:
        return 0

    opt_out: str = _load_drift_module()._OPT_OUT_MARKER
    sys.stderr.write(_format_report(hits, opt_out))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
