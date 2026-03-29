#!/usr/bin/env python3
"""Create GitHub issues for planned workflow automation features.

This script generates tracking issues for implementing a simple GitHub-native
workflow with:
- Conventional commits enforcement (conventional-pre-commit)
- Automatic semantic versioning (Release Please)
- Branch naming conventions with issue IDs
- PyCharm IDE integration
- Automatic cleanup of merged branches

Conventional commits enforcement (conventional-pre-commit) is already
implemented. Run this script to create issues that track the remaining
planned features.

See docs/WORKFLOW_AUTOMATION_PLAN.md for the complete architecture and
implementation plan.

Usage:
    python3 scripts/create_workflow_automation_issues.py
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass
class Issue:
    """GitHub issue specification."""

    title: str
    body: str
    labels: list[str]

    def create(self) -> str | None:
        """Create issue via GitHub CLI and return issue number."""
        cmd: list[str] = [
            "gh",
            "issue",
            "create",
            "--title",
            self.title,
            "--body",
            self.body,
            "--label",
            ",".join(self.labels),
        ]

        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            output: str = result.stdout.strip()
            if "/" in output:
                issue_num: str = output.split("/")[-1]
                print(f"✅ Created issue #{issue_num}: {self.title}")
                return issue_num
            return None
        except subprocess.TimeoutExpired:
            print(
                f"❌ GitHub CLI timed out creating issue: {self.title}. "
                "Check your network connection or GitHub API status.",
                file=sys.stderr,
            )
            return None
        except subprocess.CalledProcessError as e:
            print(f"❌ Error creating issue: {e.stderr}", file=sys.stderr)
            return None
        except FileNotFoundError:
            print(
                "❌ GitHub CLI not found. Install: https://cli.github.com/",
                file=sys.stderr,
            )
            sys.exit(1)


def get_issues() -> list[Issue]:
    """Define workflow automation issues.

    Returns:
        List of Issue objects defining the workflow automation tasks.
        Each issue includes a title, description, and GitHub labels.
    """
    return [
        Issue(
            title="Add Release Please for automatic semantic versioning",
            body="""## Goal

Automatically calculate versions and generate release notes on merge to main.

## How It Works

1. Merge PR with conventional commits to main
2. Release Please analyzes commits since last release
3. Calculates next version (feat→minor, fix→patch)
4. Creates "Release PR" updating VERSION + CHANGELOG
5. You merge Release PR → GitHub release published automatically

## Tasks

- [ ] Create `.github/workflows/release-please.yml`
- [ ] Create `release-please-config.json`
- [ ] Configure to update VERSION and pyproject.toml
- [ ] Test end-to-end
- [ ] Document in CONTRIBUTING.md

## Config

```yaml
# .github/workflows/release-please.yml
name: Release Please
on:
  push:
    branches: [main]
permissions:
  contents: write
  pull-requests: write
jobs:
  release:
    runs-on: ubuntu-24.04
    steps:
      - uses: googleapis/release-please-action@v4
        with:
          release-type: python
          package-name: base_env  # Must match project name in pyproject.toml
```

```json
// release-please-config.json
{
  "packages": {
    ".": {
      "release-type": "python",
      "extra-files": ["VERSION"]
    }
  }
}
```

**Note:** The `package-name` must match the `name` field in `pyproject.toml`.

⏱️ **Effort:** 30 minutes

🔗 https://github.com/googleapis/release-please
""",
            labels=["enhancement", "ci", "automation"],
        ),
        Issue(
            title="Create branch creation helper script",
            body="""## Goal

Script to create properly-named branches from issue numbers.

## Usage

```bash
make branch ISSUE=42
# Creates: feature/42-add-redis-caching
```

## Tasks

- [ ] Create `scripts/create_branch.sh`
- [ ] Fetch issue via `gh issue view`
- [ ] Parse title and labels
- [ ] Generate branch: `<type>/<id>-<slug>`
- [ ] Add Makefile target
- [ ] Document in CONTRIBUTING.md

## Script

```bash
#!/usr/bin/env bash
set -euo pipefail

ISSUE_NUM="${1:-}"
[[ -z "$ISSUE_NUM" ]] && { echo "Usage: $0 <issue-num>" >&2; exit 1; }

ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --json title,labels 2>/dev/null || {
    echo "❌ Issue #$ISSUE_NUM not found" >&2
    exit 1
})

TITLE=$(echo "$ISSUE_JSON" | jq -r .title)
LABELS=$(echo "$ISSUE_JSON" | jq -r '.labels[].name' | paste -sd,)

TYPE="feature"
[[ "$LABELS" =~ bug ]] && TYPE="fix"
[[ "$LABELS" =~ documentation ]] && TYPE="docs"

SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-50)
BRANCH="${TYPE}/${ISSUE_NUM}-${SLUG}"

echo "✅ Issue #${ISSUE_NUM}: ${TITLE}"
echo "✅ Branch: ${BRANCH}"
git checkout -b "$BRANCH"
```

⏱️ **Effort:** 15 minutes
""",
            labels=["enhancement", "git", "tooling"],
        ),
        Issue(
            title="Configure PyCharm Conventional Commit plugin",
            body="""## Goal

Install PyCharm plugin to validate commit messages BEFORE committing.

## Plugin

- **Name:** Conventional Commit
- **ID:** com.github.lppedd.idea-conventional-commit
- **URL:** https://plugins.jetbrains.com/plugin/13389-conventional-commit

## Features

- Autocomplete commit types
- Live validation
- Integrates with PyCharm commit dialog
- Shows errors before commit

## Tasks

- [ ] Document installation in CONTRIBUTING.md
- [ ] Add installation steps with screenshots
- [ ] Test in PyCharm
- [ ] Verify works with conventional-pre-commit hook

## Installation

1. PyCharm → Settings → Plugins
2. Search: "Conventional Commit"
3. Install → Restart

⏱️ **Effort:** 10 minutes

🔗 https://plugins.jetbrains.com/plugin/13389-conventional-commit
""",
            labels=["documentation", "pycharm", "enhancement"],
        ),
        Issue(
            title="Enable auto-delete merged branches on GitHub",
            body="""## Goal

Automatically clean up branches after PRs merge.

## Implementation

**GitHub Setting:**
1. Repository Settings → General
2. Scroll to "Pull Requests"
3. Check: "Automatically delete head branches"
4. Save

**That's it!** GitHub does the rest.

## Tasks

- [ ] Enable setting in GitHub
- [ ] Test by merging a PR
- [ ] Verify branch deleted
- [ ] Document in CONTRIBUTING.md
- [ ] Add local cleanup commands

## Local Cleanup

```bash
# Remove tracking for deleted remote branches
git fetch --prune

# Delete local branches that were merged
git branch --merged main | grep -v main | xargs git branch -d
```

⏱️ **Effort:** 5 minutes

🔗 https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/managing-the-automatic-deletion-of-branches
""",
            labels=["enhancement", "github", "automation"],
        ),
        Issue(
            title="Add issue and PR templates",
            body="""## Goal

Standardize issue and PR creation with templates.

## Templates

### Issue Templates (3)
1. Bug report (steps to reproduce, environment)
2. Feature request (user story, acceptance criteria)
3. Documentation (what needs documenting)

### PR Template (1)
- Description/motivation
- Related issues
- Testing performed
- Checklist (tests, lint, docs)

## Tasks

- [ ] Create `.github/ISSUE_TEMPLATE/bug_report.yml`
- [ ] Create `.github/ISSUE_TEMPLATE/feature_request.yml`
- [ ] Create `.github/ISSUE_TEMPLATE/documentation.yml`
- [ ] Create `.github/ISSUE_TEMPLATE/config.yml`
- [ ] Create `.github/PULL_REQUEST_TEMPLATE.md`
- [ ] Test in GitHub UI
- [ ] Document in CONTRIBUTING.md

## PR Template Example

```markdown
## Description
What this PR does and why.

## Related Issues
Closes #42

## Testing
- [ ] All tests pass
- [ ] Linting passes
- [ ] Manual testing done

## Checklist
- [ ] Conventional commits used
- [ ] Documentation updated
- [ ] Type hints and docstrings added
```

⏱️ **Effort:** 25 minutes

🔗 https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests
""",
            labels=["documentation", "github"],
        ),
    ]


def main() -> None:
    """Create all workflow automation issues.

    Creates GitHub issues for implementing workflow automation features.
    Prints summary of created issues and next steps to get started.
    """
    print("🚀 Creating Workflow Automation Issues")
    print("=" * 60)
    print()

    issues: list[Issue] = get_issues()
    created: list[str] = []

    for issue in issues:
        issue_num: str | None = issue.create()
        if issue_num:
            created.append(issue_num)

    print()
    print("=" * 60)
    print(f"✅ Created {len(created)} issues")
    print()
    print("View issues:")
    print("  gh issue list")
    print()
    print("Start working on first issue:")
    if created:
        print(f"  git checkout -b feature/{created[0]}-add-release-please")
        print()
        print("(Replace 'add-release-please' with your feature description)")
        print()
        print("Note: The 'make branch ISSUE=N' helper will be available")
        print("      once issue #3 (Create branch creation helper script) is complete.")


if __name__ == "__main__":
    main()
