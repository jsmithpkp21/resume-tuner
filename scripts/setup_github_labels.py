#!/usr/bin/env python3
"""Create custom GitHub labels for workflow automation organization.

Run this before creating workflow automation issues.

Usage:
    python3 scripts/setup_github_labels.py
"""

from __future__ import annotations

import subprocess
import sys


def create_label(name: str, description: str, color: str) -> str:
    """Create a GitHub label.

    Args:
        name: Label name.
        description: Label description.
        color: Label color (hex without #).

    Returns:
        "created" if newly created, "exists" if already exists, "error" on failure.
    """
    try:
        subprocess.run(
            [
                "gh",
                "label",
                "create",
                name,
                "--description",
                description,
                "--color",
                color,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        print(f"✅ Created label: {name}")
        return "created"
    except FileNotFoundError:
        print(
            "❌ GitHub CLI not found. Install: https://cli.github.com/",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print(
            f"❌ GitHub CLI timed out creating label {name}. "
            "Check your network connection or GitHub API status.",
            file=sys.stderr,
        )
        return "error"
    except subprocess.CalledProcessError as e:
        if "already exists" in e.stderr:
            print(f"ℹ️  Label already exists: {name}")
            return "exists"
        print(f"❌ Error creating label {name}: {e.stderr}", file=sys.stderr)
        return "error"


def main() -> None:
    """Create all labels."""
    print("🏷️  Setting up GitHub labels")
    print("=" * 60)
    print()

    labels: list[tuple[str, str, str]] = [
        (
            "chore",
            "Routine maintenance, refactoring, or non-feature/non-bug tasks",
            "bfdadc",
        ),
        ("enhancement", "New feature or request", "a2eeef"),
        ("bug", "Something isn't working", "d73a4a"),
        ("documentation", "Improvements or additions to documentation", "0075ca"),
        ("feature", "New feature", "0e8a16"),
        ("refactor", "Code refactoring", "cfd3d7"),
        ("test", "Testing and test infrastructure", "e4e669"),
        ("git", "Git workflow and branch management", "0052cc"),
        ("ci", "CI/CD and automation", "1d76db"),
        ("automation", "Automation and tooling", "a2eeef"),
        ("tooling", "Tools and development utilities", "c7def8"),
        ("pycharm", "PyCharm IDE integration", "fbca04"),
        ("github", "GitHub platform features", "d4c5f9"),
    ]

    created: int = 0
    exists: int = 0
    errors: int = 0

    for name, description, color in labels:
        result: str = create_label(name, description, color)
        if result == "created":
            created += 1
        elif result == "exists":
            exists += 1
        else:
            errors += 1

    print()
    print("=" * 60)
    print(f"✅ Created: {created}, ℹ️  Existing: {exists}, ❌ Errors: {errors}")
    print(f"📊 Total: {created + exists}/{len(labels)} labels ready")
    print()
    print("Next step: Run the workflow automation issue script")
    print("  python3 scripts/create_workflow_automation_issues.py")


if __name__ == "__main__":
    main()
