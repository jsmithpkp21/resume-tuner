#!/usr/bin/env python3
"""Deny-list scan for stale API references in docstrings / help-strings.

PR #364 saw three rounds of Copilot review nits because the literal
phrase `page.fill` showed up in the module docstring AND the `--live`
help string while the implementation used `Locator.press_sequentially`.
That's the kind of drift this script catches before review.

How it works:

  - Walks every `.py` and `.js` file under `src/` and `scripts/`.
    Tests are intentionally not scanned — they assert behavior, not
    document public API.
  - Searches each line against the deny-list regex (`_DENY_PATTERNS`).
  - Skips lines containing the literal string `noqa: doc-drift`
    anywhere (typically in a `# noqa: doc-drift` Python comment or
    `// noqa: doc-drift` JS comment, but a free-form mention also
    counts). Match anywhere not strictly trailing — that way a long
    line with a mid-line opt-out is still respected.
  - Exits 1 + prints `file:line: matched-text` for every hit.

The deny-list is intentionally small + project-specific. Add entries
when a real drift incident happens; remove them when the pattern is
no longer a risk. Don't expand to "everything that could conceivably
drift" — that turns into noise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Each entry is (pattern, hint). `pattern` is a compiled regex run
# against each line; `hint` is the remediation message shown alongside
# the file:line marker.
_DENY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\bpage\.fill\b"),
        "use `Locator.fill` / `Locator.press_sequentially` (PR #364)",
    ),
    (
        re.compile(r"\bpage\.click\b"),
        "use `Locator.click` (PR #364)",
    ),
    (
        re.compile(r"\bpage\.select_option\b"),
        "use `Locator.select_option` (PR #364)",
    ),
    (
        re.compile(r"\bpage\.check\b"),
        "use `Locator.check` / `Locator.uncheck` (PR #364)",
    ),
]

# Lines containing this marker are skipped — for the rare case where
# a deny-listed phrase is being deliberately quoted (e.g., this script
# itself, or a doc that's explaining the historical mistake).
_OPT_OUT_MARKER = "noqa: doc-drift"

# Directories to scan. Tests are intentionally NOT scanned: test
# files routinely reference API names (including deny-listed ones)
# as parametric inputs or assertion strings — they're asserting
# behavior, not documenting public API. Drift control only matters
# for shipped code. `src/` is the shipped Python package;
# `scripts/` holds the CLI drivers + this script's siblings.
_SCAN_ROOTS = ("src", "scripts")
_FILE_GLOBS = ("**/*.py", "**/*.js")


def _iter_source_lines() -> list[tuple[Path, int, str]]:
    """Return a list of `(path, line_number, line_text)` for every
    line in every scannable source file. Eager rather than generator
    so the caller can iterate, count, and sort without re-walking
    the tree."""
    out: list[tuple[Path, int, str]] = []
    for root in _SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for glob in _FILE_GLOBS:
            for f in sorted(base.glob(glob)):
                if not f.is_file():
                    continue
                # Skip this script itself — it has the patterns in its
                # own _DENY_PATTERNS list, which would otherwise match.
                if f.name == "check_doc_drift.py":
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for n, line in enumerate(text.splitlines(), start=1):
                    out.append((f, n, line))
    return out


def main() -> int:
    hits: list[tuple[Path, int, str, str]] = []
    for path, lineno, line in _iter_source_lines():
        if _OPT_OUT_MARKER in line:
            continue
        for pattern, hint in _DENY_PATTERNS:
            m = pattern.search(line)
            if m:
                hits.append((path, lineno, m.group(0), hint))

    if not hits:
        return 0

    sys.stderr.write(f"doc-drift-check: {len(hits)} stale API reference(s) found:\n\n")
    for path, lineno, matched, hint in hits:
        rel = path.relative_to(REPO_ROOT)
        sys.stderr.write(f"  {rel}:{lineno}: `{matched}` — {hint}\n")
    sys.stderr.write(
        f"\nFix each occurrence or add `# {_OPT_OUT_MARKER}` to the line if the "
        "reference is intentional (e.g. quoting historical API).\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
