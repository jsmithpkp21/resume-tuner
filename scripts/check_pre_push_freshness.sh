#!/usr/bin/env bash
# check_pre_push_freshness.sh — pre-push hook: block the push if upstream
# has commits the local branch doesn't.
#
# Wired in via .pre-commit-config.yaml under stages: [push]. pre-commit
# invokes this script with the same arguments + stdin contract that git's
# native pre-push hook uses:
#
#   $1 = remote name (e.g. origin)
#   $2 = remote URL  (unused here, but part of the contract)
#   stdin = one line per ref being pushed:
#       <local_ref> <local_sha> <remote_ref> <remote_sha>
#
# For each branch push, we refresh our view of the upstream branch, and
# fail closed if the upstream tip is NOT an ancestor of the local tip
# (i.e. someone else pushed commits we don't have).
#
# Bypass: PRE_PUSH_SKIP_STALE_CHECK=1 git push ...
#
# Skipped without complaint:
#   - branch deletions (local_sha == zeros)
#   - first push of a new branch (remote_sha == zeros — no upstream yet)
#   - non-branch refs (refs/tags/*, etc.)
#   - transient fetch failures (offline / no such remote branch) — let
#     git's own push handle the actual ff-vs-non-ff decision rather than
#     false-failing here.
#
# See tooling#460 for context (PR #457 retrospective).

set -euo pipefail

if [[ -n "${PRE_PUSH_SKIP_STALE_CHECK:-}" ]]; then
  exit 0
fi

remote_name="${1:-origin}"
zero_sha="0000000000000000000000000000000000000000"
exit_code=0

while read -r local_ref local_sha remote_ref remote_sha; do
  # Branch deletion: nothing to fetch or compare.
  if [[ "$local_sha" == "$zero_sha" ]]; then
    continue
  fi

  # First push of a new branch: no upstream yet, nothing to be behind.
  if [[ "$remote_sha" == "$zero_sha" ]]; then
    continue
  fi

  # Only branch pushes; skip tags and other refs.
  if [[ "$remote_ref" != refs/heads/* ]]; then
    continue
  fi

  remote_branch="${remote_ref#refs/heads/}"

  # Refresh our view of the upstream tip. If this fails (offline, or the
  # remote doesn't have this branch yet), don't block — git's own push
  # path will surface the real error.
  if ! git fetch --quiet "$remote_name" "$remote_branch" 2>/dev/null; then
    continue
  fi

  actual_remote_sha="$(git rev-parse --verify --quiet "refs/remotes/$remote_name/$remote_branch" || true)"
  if [[ -z "$actual_remote_sha" ]]; then
    continue
  fi

  # Fast-forward: upstream tip is an ancestor of local tip. Push is safe.
  if git merge-base --is-ancestor "$actual_remote_sha" "$local_sha"; then
    continue
  fi

  ahead_count="$(git rev-list --count "$local_sha..$actual_remote_sha" 2>/dev/null || echo "?")"
  printf >&2 'pre-push: remote %s/%s has %s commit(s) you do not have locally.\n' \
    "$remote_name" "$remote_branch" "$ahead_count"
  printf >&2 '         Run: git pull --rebase %s %s\n' "$remote_name" "$remote_branch"
  printf >&2 '         Bypass (force-push intent): PRE_PUSH_SKIP_STALE_CHECK=1 git push ...\n'
  exit_code=1
done

exit "$exit_code"
