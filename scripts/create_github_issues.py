#!/usr/bin/env python3
"""Create GitHub issues from task list using GitHub CLI.

This script generates GitHub issues for all outstanding tasks.
Requires: GitHub CLI (gh command) to be installed and authenticated.

Usage:
    python3 scripts/create_github_issues.py

The script will:
1. Create an issue for each task
2. Add appropriate labels (e.g., 'enhancement', 'bug', 'documentation')
3. Set assignee to you
4. Print branch creation commands for each issue
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
    priority: str = "medium"

    def create(self) -> str | None:
        """Create issue via GitHub CLI and return issue number."""
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    self.title,
                    "--body",
                    self.body,
                    "--label",
                    ",".join(self.labels),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
            # Extract issue number from URL output
            output: str = result.stdout.strip()
            if "/" in output:
                issue_num: str = output.split("/")[-1]
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
                "❌ GitHub CLI (gh) not found. Install it from: "
                "https://cli.github.com/",
                file=sys.stderr,
            )
            return None


def get_issues() -> list[Issue]:
    """Define all issues to create."""
    return [
        Issue(
            title="Add make build-playwright target to Makefile",
            body="""## Description
Add a new Makefile target to build the Playwright layer.

## Tasks
- [ ] Add `make build-playwright` target to Makefile
- [ ] Target should call `python3 scripts/prepare_playwright_layer.py`
- [ ] Add to `.PHONY` declaration
- [ ] Document in README.md under Makefile Targets
- [ ] Test that target works correctly
- [ ] Verify output files are created

## Acceptance Criteria
- [ ] `make build-playwright` successfully builds layer
- [ ] All layer files created in `layers/playwright/`
- [ ] Documentation updated
- [ ] No lint errors""",
            labels=["enhancement", "makefile"],
        ),
        Issue(
            title="Create layers/playwright/README.md documentation",
            body="""## Description
Create comprehensive documentation for the Playwright layer.

## Tasks
- [ ] Explain layer purpose and contents
- [ ] Document what's in requirements.txt (base + playwright packages)
- [ ] Explain LAYER_METADATA.toml format
- [ ] Show how to activate layer (when built)
- [ ] Include troubleshooting section
- [ ] Add examples of layer usage

## Acceptance Criteria
- [ ] README.md exists in layers/playwright/
- [ ] Covers all layer components
- [ ] Clear examples provided
- [ ] Passes documentation linting""",
            labels=["documentation", "layers"],
        ),
        Issue(
            title="Create Layer Architecture documentation",
            body="""## Description
Create comprehensive documentation explaining the layer architecture system.

## Tasks
- [ ] Create `docs/LAYER_ARCHITECTURE.md`
- [ ] Explain single-source-of-truth for layer definitions
- [ ] Document layer dependency chain (base → playwright → ...)
- [ ] Show how to add new layers
- [ ] Include architecture diagrams/descriptions

## Acceptance Criteria
- [ ] Document explains layer system clearly
- [ ] Instructions for adding new layers provided
- [ ] Dependency chain documented
- [ ] Examples included""",
            labels=["documentation", "architecture"],
        ),
        Issue(
            title="Create prepare_selenium_layer.py script",
            body="""## Description
Create a layer preparation script for Selenium, following the same pattern as prepare_playwright_layer.py.

## Tasks
- [ ] Create `scripts/prepare_selenium_layer.py`
- [ ] Use similar structure to prepare_playwright_layer.py
- [ ] Define Selenium layer requirements in layers/selenium/
- [ ] Create LAYER_METADATA.toml for Selenium layer
- [ ] Add comprehensive tests
- [ ] Document usage

## Acceptance Criteria
- [ ] Script executes without errors
- [ ] Layer files created correctly
- [ ] 80%+ test coverage
- [ ] All checks pass (ruff, black, isort, mypy, pytest)""",
            labels=["enhancement", "layers", "python"],
        ),
        Issue(
            title="Create prepare_fastapi_layer.py script",
            body="""## Description
Create a layer preparation script for FastAPI, following the same pattern as prepare_playwright_layer.py.

## Tasks
- [ ] Create `scripts/prepare_fastapi_layer.py`
- [ ] Use similar structure to prepare_playwright_layer.py
- [ ] Define FastAPI layer requirements in layers/fastapi/
- [ ] Create LAYER_METADATA.toml for FastAPI layer
- [ ] Add comprehensive tests
- [ ] Document usage

## Acceptance Criteria
- [ ] Script executes without errors
- [ ] Layer files created correctly
- [ ] 80%+ test coverage
- [ ] All checks pass (ruff, black, isort, mypy, pytest)""",
            labels=["enhancement", "layers", "python"],
        ),
        Issue(
            title="Create generic layer_builder.py base class",
            body="""## Description
Refactor layer creation scripts to use a common base class for code reuse.

## Tasks
- [ ] Create `scripts/layer_builder.py` with base class
- [ ] Define common interface for layer builders
- [ ] Extract shared logic from prepare_*_layer.py scripts
- [ ] Update prepare_playwright_layer.py to use base class
- [ ] Update prepare_selenium_layer.py to use base class
- [ ] Update prepare_fastapi_layer.py to use base class
- [ ] Add tests for base class

## Acceptance Criteria
- [ ] Base class reduces code duplication
- [ ] All layer scripts inherit from base
- [ ] All tests pass
- [ ] No functionality lost""",
            labels=["refactor", "layers", "python"],
        ),
        Issue(
            title="Create activate_layer.sh script",
            body="""## Description
Create a script to automatically activate the appropriate layer environment.

## Tasks
- [ ] Create `scripts/activate_layer.sh`
- [ ] Auto-detect which layers are available
- [ ] Generate activation instructions
- [ ] Handle layer dependencies
- [ ] Add error handling for missing layers
- [ ] Add documentation

## Acceptance Criteria
- [ ] Script runs without errors
- [ ] Correctly detects available layers
- [ ] Generates proper activation commands
- [ ] Clear error messages for failures""",
            labels=["enhancement", "scripts"],
        ),
        Issue(
            title="Add GitHub Actions CI/CD layer testing",
            body="""## Description
Extend CI/CD pipeline to build and test each layer.

## Tasks
- [ ] Add job to build Playwright layer in CI
- [ ] Add job to build Selenium layer in CI
- [ ] Add job to build FastAPI layer in CI
- [ ] Verify cross-layer compatibility
- [ ] Add caching for layer builds
- [ ] Document CI/CD layer testing

## Acceptance Criteria
- [ ] All layer builds succeed in CI
- [ ] Layer tests run successfully
- [ ] Caching reduces build time
- [ ] No breaking changes introduced""",
            labels=["ci-cd", "layers", "github-actions"],
        ),
        Issue(
            title="Create resolve_layer_deps.py script",
            body="""## Description
Create a script to detect and resolve package conflicts between layers.

## Tasks
- [ ] Create `scripts/resolve_layer_deps.py`
- [ ] Detect package conflicts between layers
- [ ] Generate warnings for incompatible combinations
- [ ] Produce dependency graph visualization
- [ ] Document usage
- [ ] Add tests

## Acceptance Criteria
- [ ] Script detects conflicts correctly
- [ ] Clear warnings generated
- [ ] Dependency graph created
- [ ] 80%+ test coverage""",
            labels=["feature", "layers", "python"],
        ),
        Issue(
            title="Add Makefile layer management targets",
            body="""## Description
Add new Makefile targets for managing layers.

## Tasks
- [ ] Add `make build-all-layers` target
- [ ] Add `make verify-layers` target
- [ ] Add `make clean-layers` target
- [ ] Add `make list-layers` target
- [ ] Update README with all layer targets
- [ ] Test all new targets

## Acceptance Criteria
- [ ] All targets work correctly
- [ ] README updated
- [ ] Documentation clear
- [ ] No lint errors""",
            labels=["enhancement", "makefile"],
        ),
        Issue(
            title="Create Layers Guide documentation",
            body="""## Description
Create comprehensive guide for using the layers system.

## Tasks
- [ ] Create `docs/LAYER_GUIDE.md`
- [ ] Document layer versioning strategy
- [ ] Add examples of layer usage
- [ ] Include troubleshooting section
- [ ] Document best practices
- [ ] Add quick start examples

## Acceptance Criteria
- [ ] Guide is clear and comprehensive
- [ ] Examples are working and tested
- [ ] Troubleshooting covers common issues
- [ ] New users can follow guide""",
            labels=["documentation", "layers"],
        ),
        Issue(
            title="Debug terminal stdout suppression issue",
            body="""## Description
Investigate and fix stdout suppression issue in PyCharm WSL terminal.

## Details
Terminal output is suppressed in PyCharm but:
- stderr works fine
- File I/O works fine
- Commands execute correctly (timestamps prove it)

This suggests either:
1. PyCharm terminal configuration issue
2. WSL configuration issue

## Tasks
- [ ] Test in native WSL terminal (outside PyCharm)
- [ ] Check PyCharm Run Configuration settings
- [ ] Check WSL ~/.bashrc for redirects
- [ ] Verify file descriptor 1 (stdout) is writable
- [ ] Document findings
- [ ] Apply appropriate fix

## Acceptance Criteria
- [ ] Terminal output works in PyCharm
- [ ] Root cause identified and fixed
- [ ] Verified in both PyCharm and native WSL
- [ ] TERMINAL_DEBUG_REPORT.md updated""",
            labels=["bug", "terminal", "wsl"],
            priority="high",
        ),
    ]


def main() -> None:
    """Main entry point."""
    print("🚀 GitHub Issue Creator")
    print("=" * 50)
    print()

    issues = get_issues()
    created_issues: dict[str, str] = {}

    print(f"📋 Found {len(issues)} issues to create")
    print()

    for i, issue in enumerate(issues, 1):
        print(f"[{i}/{len(issues)}] Creating: {issue.title}")

        issue_num = issue.create()

        if issue_num:
            print(f"✅ Created issue #{issue_num}")
            created_issues[issue.title] = issue_num

            # Suggest branch name
            branch_name = (
                f"#{issue_num}-"
                + issue.title.lower()
                .replace(" ", "-")
                .replace(".", "")
                .replace("(", "")
                .replace(")", "")[:40]
            )
            print(f"   Branch suggestion: git checkout -b {branch_name}")
        else:
            print("❌ Failed to create issue")

        print()

    # Summary
    print("=" * 50)
    print(f"✨ Created {len(created_issues)}/{len(issues)} issues")
    print()

    if created_issues:
        print("📝 Quick Reference:")
        for title, num in created_issues.items():
            print(f"   #{num}: {title}")
        print()
        print("🔗 View all issues at: https://github.com/jsmithpkp21/base_repo/issues")


if __name__ == "__main__":
    main()
