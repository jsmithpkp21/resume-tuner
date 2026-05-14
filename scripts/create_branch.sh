#!/usr/bin/env bash
set -euo pipefail

# Script to create a properly-named branch from a GitHub issue number.
# Usage: ./scripts/create_branch.sh <issue-num>
# Example: ./scripts/create_branch.sh 42

ISSUE_NUM="${1:-}"
if [[ -z "$ISSUE_NUM" ]]; then
    echo "Usage: $0 <issue-num>" >&2
    exit 1
fi

# Preflight: confirm gh is installed and authenticated before any API call.
# Two stages, both mirroring scripts/create_pr_epic.sh:
#   1. `command -v gh` — gives an install hint if gh is missing from PATH.
#      Without this, the stage-2 `gh auth status` failure would suppress
#      bash's "command not found" via its `2>/dev/null` and surface the
#      wrong remediation (auth hint instead of install hint).
#   2. `gh auth status` — gives an auth hint. A stale or expired GITHUB_TOKEN
#      env var silently overrides stored credentials and would otherwise
#      surface as a confusing "Issue not found" downstream.
if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: GitHub CLI (gh) not found in PATH." >&2
    echo "Install from https://cli.github.com/ or see docs/SETUP/GITHUB_CLI_AUTH.md" >&2
    exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
    echo "ERROR: gh is not authenticated. Run: gh auth login" >&2
    echo "If GITHUB_TOKEN is exported in your shell, verify it is valid: gh auth status" >&2
    exit 1
fi

# Fetch issue details from GitHub. stderr is intentionally NOT redirected:
# gh's native error message (e.g. "GraphQL: Could not resolve to an Issue
# with the number of 999") is more informative than our wrapper alone.
ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --json title,labels) || {
    echo "❌ Issue #$ISSUE_NUM not found (or gh call failed — see error above)" >&2
    exit 1
}

TITLE=$(echo "$ISSUE_JSON" | jq -r .title)
LABELS=$(echo "$ISSUE_JSON" | jq -r '.labels[].name' | paste -sd,)

# Determine branch type from labels. Patterns are bounded by commas (`,$LABELS,`)
# so they exact-match label names — `bug` won't accidentally hit `bugfix`. Cases
# are evaluated top-down, so the order here defines priority when an issue has
# multiple type-mapped labels (e.g. bug+chore resolves to `fix`).
TYPE="feature"
case ",$LABELS," in
    *,bug,*)                 TYPE="fix" ;;
    *,documentation,*|*,docs,*) TYPE="docs" ;;
    *,chore,*)               TYPE="chore" ;;
    *,refactor,*)            TYPE="refactor" ;;
    *,test,*)                TYPE="test" ;;
    *,ci-cd,*)               TYPE="ci" ;;
    *,feat,*)                TYPE="feat" ;;
esac

# Strip a leading conventional-commit prefix before slugifying. Without this,
# the prefix tokens leak into the slug as meaningless run-ons (e.g.
# `chore(release): cut v1.30.1 ...` → `chorerelease-cut-v1301-...`).
# Matches all Conventional Commits prefix shapes:
#   type:                  (e.g. `feat: ...`)
#   type(scope):           (e.g. `feat(scripts): ...`)
#   type!:                 (e.g. `feat!: ...`         — breaking change)
#   type(scope)!:          (e.g. `feat(scripts)!: ...`— breaking change with scope)
# The `type` alternation is restricted to the repo's allowed types from
# `commitlint.config.mjs` type-enum — keep these two lists in sync. A title
# starting with a non-allowed lowercase word + colon (e.g. `note: keep this`)
# is left untouched so the leading word survives in the slug.
TITLE_FOR_SLUG=$(echo "$TITLE" | sed -E 's/^(feat|fix|chore|docs|style|refactor|perf|test|build|ci|revert)(\([^)]+\))?!?:[[:space:]]*//')

# Generate slug from title (lowercase, hyphens, alphanumeric, max 50 chars)
SLUG=$(echo "$TITLE_FOR_SLUG" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-50)

# Fail loudly on empty slug. Reaches here for degenerate titles like `fix:` or
# `chore(scope)!:` where the prefix is the whole title — leaving a dangling
# `fix/123-` branch would be bug-bait. Fix is trivial for the contributor: edit
# the issue title to add real content and re-run.
if [[ -z "$SLUG" ]]; then
    echo "❌ Issue #${ISSUE_NUM}: title \"${TITLE}\" produced an empty slug" >&2
    echo "   (Likely the title is only a Conventional Commits prefix like \`fix:\` with no following text.)" >&2
    echo "   Edit the issue title to add real content, then re-run." >&2
    exit 1
fi

BRANCH="${TYPE}/${ISSUE_NUM}-${SLUG}"

# Output and create branch
echo "✅ Issue #${ISSUE_NUM}: ${TITLE}"
echo "✅ Branch: ${BRANCH}"
git checkout -b "$BRANCH"
