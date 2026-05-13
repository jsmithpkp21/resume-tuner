#!/usr/bin/env python3
"""Block commits that introduce new `# type: ignore` comments.

PR #364 review round 1 flagged `_HARD_SKIP_SECTIONS` for needing a
`# type: ignore[return-value]` purely because the dict literal was
untyped. Annotating it as `dict[str, FillDecision]` removed the
ignore. That pattern recurred across several PRs this session.

This script runs as a pre-commit hook. It:

  - Reads the staged diff (`git diff --cached --unified=0`).
  - Collects added lines (`+...`) that contain `# type: ignore`.
  - Fails the commit if any are found, with a remediation hint.

If the suppression is genuinely required (e.g., third-party library
returns `Any` and there's no usable stub), add an explicit error code
plus an inline reason — and bypass the check with `--no-verify` ONLY
after running `make lint` and confirming mypy can't be satisfied
without it.
"""

from __future__ import annotations

import subprocess
import sys

_PATTERN = "# type: ignore"


def _staged_diff() -> str:
    """Return the unified diff of staged changes, zero context.

    Empty when there's nothing staged (e.g., `git commit --amend` with
    no further changes); the script then short-circuits to OK. The
    pathspec is `:(glob)**/*.py` so the diff includes Python files at
    any depth (the previous `*.py` only matched repo-root files and
    silently missed staged changes under src/, scripts/, tests/).
    """
    proc = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--unified=0",
            "--no-color",
            "--",
            ":(glob)**/*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            f"check-no-type-ignore: `git diff --cached` failed:\n{proc.stderr}"
        )
        sys.exit(2)
    return proc.stdout


def main() -> int:
    diff = _staged_diff()
    if not diff:
        return 0

    current_file = ""
    current_line_target = 0  # line number in the new file
    hits: list[tuple[str, int, str]] = []

    for raw in diff.splitlines():
        # `diff --git a/foo b/foo` — capture the post-image path so we
        # can report file:line in the rejection message.
        if raw.startswith("diff --git "):
            # Format: `diff --git a/<path> b/<path>`
            parts = raw.split(" ", 3)
            if len(parts) >= 4 and parts[3].startswith("b/"):
                current_file = parts[3][2:]
            continue
        # Hunk header — `@@ -X,Y +N,M @@`. Pull the new-file start line.
        if raw.startswith("@@"):
            # Find the +N,M chunk.
            try:
                plus = raw.split("+", 1)[1].split(" ", 1)[0]
                start_str = plus.split(",", 1)[0]
                current_line_target = int(start_str)
            except (IndexError, ValueError):
                # Malformed hunk header — skip; we'll just not report
                # line numbers for this region.
                current_line_target = 0
            continue
        # Added line.
        if raw.startswith("+") and not raw.startswith("+++"):
            content = raw[1:]
            if _PATTERN in content:
                hits.append((current_file, current_line_target, content.rstrip()))
            current_line_target += 1
        # Context / removed lines don't bump the new-file counter
        # except via the next hunk header — `--unified=0` means there
        # shouldn't be any context lines, but `-` removed lines also
        # don't advance the new-file counter, so do nothing.

    if not hits:
        return 0

    sys.stderr.write(
        f"check-no-type-ignore: {len(hits)} new `# type: ignore` "
        "comment(s) in staged changes:\n\n"
    )
    for path, lineno, line in hits:
        sys.stderr.write(f"  {path}:{lineno}: {line.strip()}\n")
    sys.stderr.write(
        "\nPrefer an explicit type annotation over `# type: ignore`. If "
        "the suppression is truly necessary, run `make lint` to confirm "
        "mypy can't be satisfied without it, then commit with "
        "`--no-verify` and add a reason comment alongside the ignore.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
