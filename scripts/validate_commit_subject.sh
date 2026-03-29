#!/usr/bin/env bash
# Validate that the commit message subject line (first line) does not end with a period.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "ERROR: commit message file path must be provided as the first argument." >&2
  exit 1
fi

if [[ ! -r "$1" ]]; then
  echo "ERROR: commit message file '$1' does not exist or is not readable." >&2
  exit 1
fi

msg=$(head -n 1 "$1")

# Trim trailing whitespace before checking for a final period.
subject="${msg%"${msg##*[![:space:]]}"}"

if [[ "$subject" =~ \.$ ]]; then
  echo "ERROR: Commit message should not end with a period: $subject" >&2
  exit 1
fi

exit 0
