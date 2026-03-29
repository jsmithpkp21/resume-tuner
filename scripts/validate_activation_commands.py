#!/usr/bin/env python3
"""Validate markdown docs do not use fragile env activation command patterns."""

from __future__ import annotations

import argparse
import pathlib
import re
from dataclasses import dataclass

FRAGILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"source\s+~/envs/\$\(git\s+remote\s+get-url\s+origin"),
    re.compile(
        r"bash\s+-lc\s+[\"']source\s+~/envs/\$\(git\s+remote\s+get-url" r"\s+origin"
    ),
)

EXCLUDE_DIRS = {
    ".git",
    ".idea",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
}


@dataclass(frozen=True)
class Finding:
    path: pathlib.Path
    line: int
    text: str


def iter_markdown_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for path in root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def scan_file(path: pathlib.Path) -> list[Finding]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        lines = path.read_text(encoding="latin-1").splitlines()

    findings: list[Finding] = []
    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        # Skip lines that are clearly showing anti-patterns as examples in checklists
        if stripped.startswith("- `") or stripped.startswith("- [ ]"):
            continue

        for pattern in FRAGILE_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path=path, line=idx, text=line.strip()))
                break
    return findings


def run(root: pathlib.Path) -> int:
    findings: list[Finding] = []
    for md in iter_markdown_files(root):
        findings.extend(scan_file(md))

    if not findings:
        print("OK: no fragile activation command patterns found in markdown docs.")
        return 0

    print("ERROR: fragile activation command patterns found:")
    for finding in findings:
        rel = finding.path.relative_to(root)
        print(f"- {rel}:{finding.line}: {finding.text}")

    print("\nUse the robust pattern:")
    print(
        "REPO_NAME=\"$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\\.git$||')\""
    )
    print(
        'REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"'
    )
    print('source ~/envs/"${REPO_NAME}"-env/bin/activate')
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate markdown docs for fragile activation commands."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    args = parser.parse_args()
    return run(pathlib.Path(args.root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
