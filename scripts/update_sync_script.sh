#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR_INPUT="${1:-$(pwd)}"
if ! TARGET_DIR="$(cd -- "$TARGET_DIR_INPUT" && pwd -P)"; then
  echo "ERROR: Target directory does not exist or is not accessible: $TARGET_DIR_INPUT" >&2
  exit 1
fi

TARGET_SCRIPT="$TARGET_DIR/scripts/sync_tooling.sh"
if [ ! -f "$TARGET_SCRIPT" ]; then
  echo "ERROR: Target sync script not found: $TARGET_SCRIPT" >&2
  exit 1
fi

assert_no_symlink_ancestors() {
  local path="$1"
  while [ -n "$path" ] && [ "$path" != "/" ] && [ "$path" != "." ]; do
    if [ -L "$path" ]; then
      echo "ERROR: Path component is a symlink and not allowed for this operation: $path" >&2
      exit 1
    fi
    path="$(dirname "$path")"
  done
}

assert_no_symlink_ancestors "$TARGET_SCRIPT"

SCRIPT_DIR="$(cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
POTENTIAL_TOOLING_DIR="$(dirname "$SCRIPT_DIR")"

is_valid_tooling_dir() {
  local dir="$1"
  [ -d "$dir" ] \
    && [ -f "$dir/scripts/sync_tooling.sh" ] \
    && [ -f "$dir/Makefile" ] \
    && [ -f "$dir/.tooling-sync-manifest.toml" ] \
    && [ ! -f "$dir/.tooling-sync-manifest.lock" ]
}

TOOLING_SOURCE_DIR=""
if [ -n "${TOOLING_DIR:-}" ]; then
  if is_valid_tooling_dir "$TOOLING_DIR"; then
    TOOLING_SOURCE_DIR="$(cd -- "$TOOLING_DIR" && pwd -P)"
  else
    echo "ERROR: TOOLING_DIR is set but invalid: $TOOLING_DIR" >&2
    echo "Expected: scripts/sync_tooling.sh, Makefile, .tooling-sync-manifest.toml, and no .tooling-sync-manifest.lock" >&2
    exit 1
  fi
elif is_valid_tooling_dir "$POTENTIAL_TOOLING_DIR" && [ "$POTENTIAL_TOOLING_DIR" != "$TARGET_DIR" ]; then
  TOOLING_SOURCE_DIR="$(cd -- "$POTENTIAL_TOOLING_DIR" && pwd -P)"
elif is_valid_tooling_dir "$TARGET_DIR/../tooling"; then
  TOOLING_SOURCE_DIR="$(cd -- "$TARGET_DIR/../tooling" && pwd -P)"
else
  echo "ERROR: Could not locate tooling source directory." >&2
  echo "Set TOOLING_DIR=/path/to/tooling or place tooling as ../tooling next to the target repo." >&2
  exit 1
fi

SOURCE_SCRIPT="$TOOLING_SOURCE_DIR/scripts/sync_tooling.sh"
if [ ! -f "$SOURCE_SCRIPT" ]; then
  echo "ERROR: Source sync script not found: $SOURCE_SCRIPT" >&2
  exit 1
fi

assert_no_symlink_ancestors "$SOURCE_SCRIPT"

echo "=== update-sync-script ==="
echo "Source: $SOURCE_SCRIPT"
echo "Target: $TARGET_SCRIPT"
echo ""
echo "Diff summary:"
if cmp -s "$TARGET_SCRIPT" "$SOURCE_SCRIPT"; then
  echo "No changes detected. Target script is already up to date."
  exit 0
fi

# Portable summary and preview for reviewers before confirmation.
if command -v diff >/dev/null 2>&1; then
  diff -u "$TARGET_SCRIPT" "$SOURCE_SCRIPT" | sed -n '1,80p' || true
else
  echo "(diff command not available; cannot show textual diff preview)"
fi

echo ""
echo "Type 'yes' to copy source script into target:"
if ! read -r confirm; then
  echo "Aborted: confirmation must be exactly 'yes'." >&2
  exit 1
fi
if [ "$confirm" != "yes" ]; then
  echo "Aborted: confirmation must be exactly 'yes'." >&2
  exit 1
fi

cp -p "$SOURCE_SCRIPT" "$TARGET_SCRIPT"

SOURCE_REF="unknown"
if command -v git >/dev/null 2>&1; then
  if git -C "$TOOLING_SOURCE_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    SOURCE_REF="$(git -C "$TOOLING_SOURCE_DIR" describe --tags --always 2>/dev/null || git -C "$TOOLING_SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  fi
fi

echo "Updated scripts/sync_tooling.sh from $TOOLING_SOURCE_DIR ($SOURCE_REF)"
