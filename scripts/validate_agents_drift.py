#!/usr/bin/env python3
"""Validate AGENTS.md and .github/copilot-instructions.md stay in sync.

AGENTS.md is the source of truth; .github/copilot-instructions.md is its
mirror for the GitHub Copilot SWE agent. The two files have intentionally
different structure (the Copilot variant omits some sections and adds a
Copilot-specific Initial Commit Fix appendix), so this checker does not do
a byte-level diff. Instead it asserts that a curated set of substantive
policies appears in both files. Drift here means a rule was edited or
removed in one file without the other; formatting or wording differences
are not flagged.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from dataclasses import dataclass

AGENTS_PATH = pathlib.Path("AGENTS.md")
COPILOT_PATH = pathlib.Path(".github/copilot-instructions.md")


@dataclass(frozen=True)
class Invariant:
    invariant_id: str
    pattern: re.Pattern[str]
    description: str


INVARIANTS: tuple[Invariant, ...] = (
    Invariant(
        "planning_gate",
        re.compile(r"Planning Gate.*\n(?:.*\n){0,8}.*plan ready", re.IGNORECASE),
        "Planning Gate section requiring explicit `plan ready` before edits",
    ),
    Invariant(
        "agents_local_overrides",
        re.compile(r"AGENTS_LOCAL\.md"),
        "AGENTS_LOCAL.md override layering reference",
    ),
    Invariant(
        "quick_commands_setup",
        re.compile(r"make setup"),
        "Quick Commands listing `make setup`",
    ),
    Invariant(
        "conventional_commits",
        re.compile(r"Conventional commits are mandatory", re.IGNORECASE),
        "Conventional commits enforcement statement",
    ),
    Invariant(
        "main_branch_blocked",
        re.compile(r"commit/push to\s+`?main`?\s+is blocked", re.IGNORECASE),
        "Direct commit/push to main is blocked policy",
    ),
    Invariant(
        "semver_pins",
        re.compile(r"strict semver tag pins", re.IGNORECASE),
        "GitHub Actions strict semver tag pin policy",
    ),
    Invariant(
        "action_lock_alignment",
        re.compile(r"workflow-action-lock\.json"),
        "Reference to .github/workflow-action-lock.json for action refs",
    ),
    Invariant(
        "branch_base_policy",
        re.compile(r"Branch base policy", re.IGNORECASE),
        "Branch base policy (main vs active epic) for issue branches",
    ),
    Invariant(
        "wsl_path_handling",
        re.compile(r"WSL Path Handling", re.IGNORECASE),
        "WSL Path Handling section",
    ),
    Invariant(
        "wsl_unc_translation",
        re.compile(r"wsl\.localhost"),
        "UNC -> Linux path translation rule for WSL editors",
    ),
    Invariant(
        "gh_auth_status_preflight",
        re.compile(r"gh auth status"),
        "gh CLI preflight requirement before scripted gh calls",
    ),
    Invariant(
        "github_token_warning",
        re.compile(r"Never export\s+`?GITHUB_TOKEN`?", re.IGNORECASE),
        "Never export GITHUB_TOKEN as a static value warning",
    ),
    Invariant(
        "sync_security_invariants",
        re.compile(r"path traversal", re.IGNORECASE),
        "scripts/sync_tooling.sh path-traversal security invariant",
    ),
    Invariant(
        "copilot_review_convention",
        re.compile(r"@copilot"),
        "PR review convention for copilot/* branches",
    ),
    Invariant(
        "files_to_read",
        re.compile(r"Files to Read Before Editing Core Logic", re.IGNORECASE),
        "Files to Read Before Editing Core Logic section",
    ),
)


def _load(root: pathlib.Path, rel: pathlib.Path) -> tuple[pathlib.Path, str | None]:
    full = root / rel
    if not full.is_file():
        return full, None
    return full, full.read_text(encoding="utf-8")


def check(root: pathlib.Path) -> int:
    agents_full, agents_text = _load(root, AGENTS_PATH)
    copilot_full, copilot_text = _load(root, COPILOT_PATH)

    missing_files: list[pathlib.Path] = []
    if agents_text is None:
        missing_files.append(agents_full)
    if copilot_text is None:
        missing_files.append(copilot_full)

    if missing_files:
        for path in missing_files:
            print(f"ERROR: required file not found: {path}", file=sys.stderr)
        return 1

    assert agents_text is not None
    assert copilot_text is not None

    failures: list[str] = []

    banner = "Synced from AGENTS.md"
    if banner not in copilot_text:
        failures.append(
            f"{COPILOT_PATH}: missing source-of-truth banner "
            f'(expected substring "{banner}")'
        )

    for invariant in INVARIANTS:
        in_agents = bool(invariant.pattern.search(agents_text))
        in_copilot = bool(invariant.pattern.search(copilot_text))
        if in_agents and in_copilot:
            continue
        if not in_agents and not in_copilot:
            failures.append(
                f"invariant `{invariant.invariant_id}` "
                f"({invariant.description}) is missing from BOTH files"
            )
        elif not in_agents:
            failures.append(
                f"invariant `{invariant.invariant_id}` "
                f"({invariant.description}) present in {COPILOT_PATH} "
                f"but missing from {AGENTS_PATH} -- "
                "AGENTS.md is the source of truth"
            )
        else:
            failures.append(
                f"invariant `{invariant.invariant_id}` "
                f"({invariant.description}) present in {AGENTS_PATH} "
                f"but missing from {COPILOT_PATH} -- "
                "update copilot-instructions.md to match"
            )

    if failures:
        print(
            "ERROR: AGENTS.md / copilot-instructions.md drift detected:",
            file=sys.stderr,
        )
        for line in failures:
            print(f"- {line}", file=sys.stderr)
        return 1

    print(
        "OK: AGENTS.md and .github/copilot-instructions.md agree on all "
        f"{len(INVARIANTS)} tracked invariants."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate AGENTS.md and .github/copilot-instructions.md remain "
            "in sync on tracked policy invariants."
        ),
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    args = parser.parse_args(argv)
    return check(pathlib.Path(args.root).resolve())


if __name__ == "__main__":
    sys.exit(main())
