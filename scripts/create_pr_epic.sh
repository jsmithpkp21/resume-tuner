#!/usr/bin/env bash
set -euo pipefail

# Open a draft PR from the current issue branch to the parent epic branch
# (or main when no epic is detected).
#
# Inputs (env vars seed the values; matching key=value args override them):
#   ISSUE / PR_EPIC_ISSUE  required, positive integer
#   EPIC  / PR_EPIC_EPIC   explicit epic branch (must exist on origin)
#   BASE  / PR_EPIC_BASE   explicit base branch (used as-is)
#   TITLE / PR_EPIC_TITLE  PR title (defaults to the issue title)
#   READY / PR_EPIC_READY  set to 1 to skip --draft
#
# The Makefile target uses target-scoped exports of PR_EPIC_* so that values
# such as TITLE='$(date)' cannot escape the recipe and execute as a command
# substitution; direct script callers (and tests) can still pass key=value
# args, which override any env vars supplied for the same field.
#
# Usage:
#   scripts/create_pr_epic.sh ISSUE=<num> [EPIC=<branch>] [BASE=<branch>] [TITLE=<text>] [READY=1]
#
# Base resolution order (first match wins):
#   1. BASE=<branch>      - explicit override; used as-is.
#   2. EPIC=<branch>      - explicit epic branch; must exist on origin.
#   3. Auto-detect        - GitHub sub-issue parent + epic/<parent>-* on origin.
#   4. main (with WARN)   - no parent epic found.
#
# Preflight failures exit non-zero with an actionable message.

ISSUE="${PR_EPIC_ISSUE:-}"
EPIC="${PR_EPIC_EPIC:-}"
BASE="${PR_EPIC_BASE:-}"
READY="${PR_EPIC_READY:-}"
TITLE="${PR_EPIC_TITLE:-}"
for arg in "$@"; do
    case "$arg" in
        ISSUE=*) ISSUE="${arg#ISSUE=}" ;;
        EPIC=*)  EPIC="${arg#EPIC=}" ;;
        BASE=*)  BASE="${arg#BASE=}" ;;
        READY=*) READY="${arg#READY=}" ;;
        TITLE=*) TITLE="${arg#TITLE=}" ;;
        *) echo "ERROR: unknown argument: $arg" >&2; exit 2 ;;
    esac
done

if [[ -z "$ISSUE" ]]; then
    echo "ERROR: ISSUE is required." >&2
    echo "Usage: $0 ISSUE=<num> [EPIC=<branch>] [BASE=<branch>] [TITLE=<text>] [READY=1]" >&2
    exit 2
fi
if ! [[ "$ISSUE" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: ISSUE must be a positive integer, got: '$ISSUE'" >&2
    exit 2
fi

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

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not inside a git working tree." >&2
    echo "Run this from a checkout of the project (cd into the repo and retry)." >&2
    exit 1
fi
if ! git remote get-url origin >/dev/null 2>&1; then
    echo "ERROR: this repo has no 'origin' remote." >&2
    echo "Add one with: git remote add origin <url> (and push the branch first)." >&2
    exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    echo "ERROR: cannot run pr-epic on '$BRANCH'. Switch to an issue branch first (make branch ISSUE=$ISSUE)." >&2
    exit 1
fi
if [[ "$BRANCH" == epic/* ]]; then
    echo "ERROR: cannot run pr-epic on an epic branch ('$BRANCH'). Open this from a child issue branch." >&2
    exit 1
fi
# Match the canonical convention `<type>/<issue>-<slug>` so that ISSUE=87 does
# not accidentally match feature/187-... or feature/870-... .
if [[ "$BRANCH" != */"$ISSUE"-* ]]; then
    echo "ERROR: current branch '$BRANCH' does not match issue #$ISSUE." >&2
    echo "Expected the canonical naming '<type>/$ISSUE-<slug>'. Either switch to" >&2
    echo "the matching branch (make branch ISSUE=$ISSUE) or rename the current one." >&2
    exit 1
fi

if ! git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
    echo "INFO: branch '$BRANCH' is not on origin yet; pushing now." >&2
    git push -u origin "$BRANCH"
fi

PR_BASE=""
if [[ -n "$BASE" ]]; then
    PR_BASE="$BASE"
    echo "INFO: using explicit BASE=$PR_BASE" >&2
elif [[ -n "$EPIC" ]]; then
    if ! git ls-remote --exit-code --heads origin "$EPIC" >/dev/null 2>&1; then
        echo "ERROR: explicit EPIC='$EPIC' does not exist on origin." >&2
        exit 1
    fi
    PR_BASE="$EPIC"
    echo "INFO: using explicit EPIC=$PR_BASE" >&2
else
    if ! REPO_SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null); then
        echo "ERROR: gh could not identify a GitHub repo for the current checkout." >&2
        echo "Possible causes: 'origin' points to a non-GitHub host, the repo is" >&2
        echo "private and your gh user lacks access, or the network is unreachable." >&2
        echo "Override the base manually with: BASE=main or EPIC=<branch>." >&2
        exit 1
    fi
    OWNER="${REPO_SLUG%%/*}"
    NAME="${REPO_SLUG##*/}"
    # Distinguish "GraphQL call failed" from "issue has no parent". Both fall
    # back to main, but they get different WARN messages so a transient API
    # error does not look like a deliberate "no parent" decision.
    PARENT_NUM=""
    if ! GRAPHQL_OUT=$(gh api graphql \
        -F owner="$OWNER" -F name="$NAME" -F num="$ISSUE" \
        -f query='query($owner:String!,$name:String!,$num:Int!){repository(owner:$owner,name:$name){issue(number:$num){parent{number}}}}' \
        --jq '.data.repository.issue.parent.number // empty' 2>&1); then
        echo "WARN: GitHub parent-issue query failed; auto-detect skipped." >&2
        echo "      Falling back to main. Override with EPIC=<branch> or BASE=<branch>." >&2
        PR_BASE="main"
    else
        PARENT_NUM="$GRAPHQL_OUT"
        if [[ -n "$PARENT_NUM" ]]; then
            # Wrap ls-remote separately so a transient origin/network error
            # surfaces an actionable WARN instead of dying silently under
            # `set -euo pipefail`.
            if ! LSREMOTE_OUT=$(git ls-remote --heads origin "epic/${PARENT_NUM}-*" 2>&1); then
                echo "WARN: git ls-remote for epic/${PARENT_NUM}-* failed; auto-detect aborted." >&2
                echo "      Falling back to main. Override with EPIC=<branch> or BASE=<branch>." >&2
                PR_BASE="main"
            else
                AUTO_EPIC=$(printf '%s\n' "$LSREMOTE_OUT" \
                    | awk 'NR==1 { sub(/^refs\/heads\//, "", $2); print $2 }')
                if [[ -n "$AUTO_EPIC" ]]; then
                    PR_BASE="$AUTO_EPIC"
                    echo "INFO: auto-detected parent epic #$PARENT_NUM -> base=$PR_BASE" >&2
                else
                    echo "WARN: parent issue #$PARENT_NUM has no epic/$PARENT_NUM-* branch on origin; falling back to main." >&2
                    PR_BASE="main"
                fi
            fi
        else
            echo "WARN: no parent epic detected for #$ISSUE; falling back to main. (Override with EPIC=<branch> or BASE=<branch>.)" >&2
            PR_BASE="main"
        fi
    fi
fi

# Always validate the issue exists / is accessible, even when TITLE is set,
# so we never open a PR referencing a nonexistent or unreadable issue. Use
# `-q .title` so gh extracts the field itself; this avoids a hard `jq`
# dependency on top of gh + git + awk.
if ! FETCHED_TITLE=$(gh issue view "$ISSUE" --json title -q .title 2>/dev/null); then
    echo "ERROR: could not read issue #$ISSUE via gh." >&2
    echo "Verify the number, your gh authentication, and that you have access." >&2
    exit 1
fi
if [[ -z "$TITLE" ]]; then
    TITLE="$FETCHED_TITLE"
fi

GH_ARGS=(pr create --base "$PR_BASE" --head "$BRANCH" --title "$TITLE" --body "Closes #${ISSUE}")
if [[ "$READY" != "1" ]]; then
    GH_ARGS+=(--draft)
fi

URL=$(gh "${GH_ARGS[@]}")
echo "$URL"
