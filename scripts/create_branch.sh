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

# Fetch issue details from GitHub
ISSUE_JSON=$(gh issue view "$ISSUE_NUM" --json title,labels 2>/dev/null || {
    echo "❌ Issue #$ISSUE_NUM not found" >&2
    exit 1
})

TITLE=$(echo "$ISSUE_JSON" | jq -r .title)
LABELS=$(echo "$ISSUE_JSON" | jq -r '.labels[].name' | paste -sd,)

# Determine branch type from labels
TYPE="feature"
if [[ "$LABELS" =~ bug ]]; then
    TYPE="fix"
elif [[ "$LABELS" =~ documentation ]]; then
    TYPE="docs"
fi

# Generate slug from title (lowercase, hyphens, alphanumeric, max 50 chars)
SLUG=$(echo "$TITLE" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd '[:alnum:]-' | cut -c1-50)
BRANCH="${TYPE}/${ISSUE_NUM}-${SLUG}"

# Output and create branch
echo "✅ Issue #${ISSUE_NUM}: ${TITLE}"
echo "✅ Branch: ${BRANCH}"
git checkout -b "$BRANCH"
