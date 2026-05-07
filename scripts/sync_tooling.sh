#!/usr/bin/env bash
set -euo pipefail

# Parse flags first, then positional args:
#   $1 -> tooling ref/version
#   $2 -> target directory
NO_DELETE=false
POSITIONAL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --no-delete)
      NO_DELETE=true
      ;;
    --*)
      echo "ERROR: Unknown option: $arg"
      exit 1
      ;;
    *)
      POSITIONAL_ARGS+=("$arg")
      ;;
  esac
done
set -- "${POSITIONAL_ARGS[@]}"

if [ "${SYNC_NO_DELETE:-}" = "1" ] || [ "${SYNC_NO_DELETE:-}" = "true" ]; then
  NO_DELETE=true
fi

# Target directory can be passed as second argument or defaults to current directory
TARGET_DIR="${2:-$(pwd)}"

# Try to read version and repo from tooling.toml in target directory
if [ -f "$TARGET_DIR/tooling.toml" ]; then
  TOOLING_VERSION_FROM_TOML=$(grep -E '^version\s*=' "$TARGET_DIR/tooling.toml" | head -1 | sed -E 's/version\s*=\s*"(.*)"/\1/' || echo "")
  TOOLING_REPO_FROM_TOML=$(grep -E '^repo\s*=' "$TARGET_DIR/tooling.toml" | head -1 | sed -E 's/repo\s*=\s*"(.*)"/\1/' || echo "")
else
  TOOLING_VERSION_FROM_TOML=""
  TOOLING_REPO_FROM_TOML=""
fi

# Override with command line args or env vars, or use toml values, or use defaults
TOOLING_VERSION="${1:-${TOOLING_VERSION_FROM_TOML:-v1.0.0}}"
TOOLING_REPO="${TOOLING_REPO:-${TOOLING_REPO_FROM_TOML:-}}"

# Determine TOOLING_DIR based on whether we're in the tooling repo itself or a project using it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POTENTIAL_TOOLING_DIR="$(dirname "$SCRIPT_DIR")"

# Get absolute path of TARGET_DIR for comparison
TARGET_DIR_ABS="$(cd "$TARGET_DIR" && pwd)"

# Resolve a Python interpreter for sync-time invocations. Post-sync steps
# (merge_pyproject.py, .release-please-config.json updater) depend on
# third-party packages (tomli_w) and tomllib (3.11+), which the system python3
# on PATH may lack. Mirror the venv layout used by scripts/create_env.sh so
# `make sync-tooling` runs with the same interpreter as `make lint/test/check`.
#
# Resolution order:
#   1. <TARGET>/.venv/bin/python      (in-tree venv, used by some repos)
#   2. ~/envs/<basename>-env/bin/python (matches scripts/create_env.sh)
#   3. python3 on PATH                 (fallback; warning emitted on failure)
SYNC_PYTHON="python3"
SYNC_PYTHON_FROM_VENV=false
SYNC_PYTHON_VENV_PATH=""
SYNC_PYTHON_ENVS_CANDIDATE="$HOME/envs/$(basename "$TARGET_DIR_ABS")-env/bin/python"

if [ -x "$TARGET_DIR_ABS/.venv/bin/python" ]; then
  SYNC_PYTHON="$TARGET_DIR_ABS/.venv/bin/python"
  SYNC_PYTHON_FROM_VENV=true
  SYNC_PYTHON_VENV_PATH="$TARGET_DIR_ABS/.venv"
elif [ -x "$SYNC_PYTHON_ENVS_CANDIDATE" ]; then
  SYNC_PYTHON="$SYNC_PYTHON_ENVS_CANDIDATE"
  SYNC_PYTHON_FROM_VENV=true
  SYNC_PYTHON_VENV_PATH="${SYNC_PYTHON_ENVS_CANDIDATE%/bin/python}"
fi

is_valid_tooling_dir() {
  local dir="$1"
  [ -d "$dir" ] && [ -f "$dir/scripts/sync_tooling.sh" ] && [ -f "$dir/Makefile" ]
}

# Portable path normalization helper (works on macOS/BSD where `realpath -m` is unavailable).
# Always exits 0; returns empty string on invalid/escaping paths (caller checks emptiness).
normalize_sync_path() {
  local file_path="$1"

  if [ -x "$SYNC_PYTHON" ] || command -v "$SYNC_PYTHON" >/dev/null 2>&1; then
    "$SYNC_PYTHON" - "$TARGET_DIR_ABS" "$file_path" 2>/dev/null <<'PY' || true
import os
import sys

target_dir = os.path.abspath(sys.argv[1])
file_path = sys.argv[2]

candidate = os.path.normpath(os.path.join(target_dir, file_path))
try:
    common = os.path.commonpath([target_dir, candidate])
except ValueError:
    sys.exit(0)

if common != target_dir:
    sys.exit(0)

print(candidate)
PY
    return
  fi

  # Fallback: shell-based path normalization (works when path doesn't exist yet).
  # This approach normalizes the path without requiring it to exist on disk.
  # It handles: . removal, .. processing (walking up dirs), and trailing slashes.
  local target_abs="$TARGET_DIR_ABS"
  local normalized="$file_path"

  # Remove leading ./ if present
  normalized="${normalized#./}"

  # Split into segments and process (basic .. handling)
  local result="" segment
  IFS='/' read -r -a segments <<< "$normalized"

  for segment in "${segments[@]}"; do
    case "$segment" in
      "" | ".")
        # Skip empty segments and current dir references
        ;;
      "..")
        # Remove last segment (go up one directory)
        result="${result%/*}"
        ;;
      *)
        # Append normal segment
        result="${result:+$result/}$segment"
        ;;
    esac
  done

  # Construct final path and verify it's under target_dir
  local final_path="$target_abs${result:+/$result}"

  # Basic containment check (if final_path starts with target_abs + /)
  if [[ "$final_path" == "$target_abs"* ]]; then
    echo "$final_path"
  fi
}

# SECURITY: Verify target path is safe from symlink traversal.
# Rejects if any parent directory component is a symlink (attacker could have
# placed symlink to /etc/ inside the repo), or if destination file is a symlink.
validate_no_symlink_traversal() {
  local target_file="$1"

  # Accept repo-relative path; if absolute path is passed, strip TARGET_DIR_ABS prefix.
  local remaining="$target_file"
  if [[ "$remaining" == /* ]]; then
    if [[ "$remaining" == "$TARGET_DIR_ABS"/* ]]; then
      remaining="${remaining#"$TARGET_DIR_ABS"/}"
    else
      echo "ERROR: Symlink validation path is outside target directory: $target_file" >&2
      return 1
    fi
  fi

  # Check each component of the destination path under TARGET_DIR_ABS.
  local current_path="$TARGET_DIR_ABS"

  while [ -n "$remaining" ]; do
    # Extract first segment
    remaining="${remaining#/}"
    local segment="${remaining%%/*}"
    remaining="${remaining#$segment}"
    remaining="${remaining#/}"

    [ -z "$segment" ] && continue

    current_path="$current_path/$segment"

    # If path component doesn't exist yet, we're safe
    if [ ! -e "$current_path" ]; then
      continue
    fi

    # If it exists but is a symlink, REJECT (symlink traversal attempt)
    if [ -L "$current_path" ]; then
      echo "ERROR: Path component is a symlink (symlink traversal): $current_path" >&2
      return 1
    fi
  done

  return 0
}

# SECURITY: Validate file paths to prevent directory traversal attacks
# Rejects absolute paths, parent directory references, and paths that would escape TARGET_DIR
validate_sync_path() {
  local file_path="$1"

  # Reject absolute paths
  if [[ "$file_path" == /* ]]; then
    echo "ERROR: Absolute paths not allowed: $file_path" >&2
    return 1
  fi

  # Reject explicit parent-directory traversal segments
  local part
  local -a parts
  IFS='/' read -r -a parts <<< "$file_path"
  for part in "${parts[@]}"; do
    if [ "$part" = ".." ]; then
      echo "ERROR: Parent directory references (..) not allowed: $file_path" >&2
      return 1
    fi
  done

  # Normalize and verify the resolved path stays within TARGET_DIR
  local normalized_path
  normalized_path="$(normalize_sync_path "$file_path")"

  if [ -z "$normalized_path" ] || [[ "$normalized_path" != "$TARGET_DIR_ABS"/* ]]; then
    echo "ERROR: Path would escape target directory: $file_path" >&2
    return 1
  fi

  return 0
}

# SECURITY CHECK: Prevent running sync-tooling from within the actual tooling repo source
# This prevents accidentally syncing the tooling repo to itself
# Detection method: Check git remote URL - the tooling repo has 'tooling' in its remote
# Exception: Allow temp directories (for testing) - these are typically under /tmp or /var/tmp
IS_TOOLING_REPO=false
if [ -d "$POTENTIAL_TOOLING_DIR/.git" ]; then
  REMOTE_URL=$(cd "$POTENTIAL_TOOLING_DIR" && git config --get remote.origin.url 2>/dev/null || echo "")
  if [[ "$REMOTE_URL" == *"tooling"* ]]; then
    IS_TOOLING_REPO=true
  fi
fi

if [ "$IS_TOOLING_REPO" = true ] && [ "$TARGET_DIR_ABS" = "$POTENTIAL_TOOLING_DIR" ]; then
  case "$TARGET_DIR_ABS" in
    /tmp/*|/var/tmp/*)
      echo "⚠ Warning: Running sync-tooling in temp directory: $TARGET_DIR_ABS"
      ;;
    *)
      echo "ERROR: Cannot run sync-tooling from within the tooling repository itself."
      echo ""
      echo "The tooling repository should not sync to itself."
      echo "Please run this command from a project that uses tooling (e.g., base_repo)."
      echo ""
      echo "Example:"
      echo "  cd /path/to/your/project"
      echo "  make sync-tooling"
      echo ""
      exit 1
      ;;
  esac
fi

# Resolve tooling source in this order:
# 1) pre-set TOOLING_DIR environment variable
# 2) script-adjacent tooling directory (archive/bootstrap use-case)
# 3) sibling ../tooling near target project
# 4) tooling repo itself when invoked from real tooling checkout
PREFERRED_TOOLING_DIR="${TOOLING_DIR:-}"
TOOLING_DIR=""

if [ -n "$PREFERRED_TOOLING_DIR" ]; then
  if is_valid_tooling_dir "$PREFERRED_TOOLING_DIR"; then
    TOOLING_DIR="$(cd "$PREFERRED_TOOLING_DIR" && pwd)"
  else
    echo "ERROR: TOOLING_DIR is set but invalid: $PREFERRED_TOOLING_DIR"
    echo "Expected files: scripts/sync_tooling.sh and Makefile"
    exit 1
  fi
fi

if [ -z "$TOOLING_DIR" ] && [ "$POTENTIAL_TOOLING_DIR" != "$TARGET_DIR_ABS" ] && is_valid_tooling_dir "$POTENTIAL_TOOLING_DIR"; then
  TOOLING_DIR="$POTENTIAL_TOOLING_DIR"
fi

if [ -z "$TOOLING_DIR" ] && is_valid_tooling_dir "$TARGET_DIR/../tooling"; then
  TOOLING_DIR="$(cd "$TARGET_DIR/../tooling" && pwd)"
fi

if [ -z "$TOOLING_DIR" ] && [ "$IS_TOOLING_REPO" = true ]; then
  TOOLING_DIR="$POTENTIAL_TOOLING_DIR"
fi

# Determine the source for syncing
# Priority:
# 1) local git checkout
# 2) local filesystem archive/extracted tooling (no .git)
# 3) GitHub (currently not implemented)
USE_LOCAL_GIT=false
USE_LOCAL_FILESYSTEM=false

if [ -n "$TOOLING_DIR" ]; then
  if git -C "$TOOLING_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    USE_LOCAL_GIT=true
  else
    USE_LOCAL_FILESYSTEM=true
  fi
elif [ -n "$TOOLING_REPO" ]; then
  : # GitHub source configured; handled by explicit not-implemented branch below
else
  echo "ERROR: Could not find tooling repository."
  echo "Either:"
  echo "  1. Set TOOLING_DIR to a local tooling checkout/archive"
  echo "  2. Place tooling repo at ../tooling relative to this project"
  echo "  3. Set TOOLING_REPO in tooling.toml or environment"
  exit 1
fi
# Some files are intentionally empty in tooling (for package/module markers).
is_allowed_empty_file() {
  local path="$1"
  case "$path" in
    "scripts/__init__.py")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Consumer-local files that should be preserved even if they were previously
# managed and later removed from the sync manifest.
is_preserved_local_stale_file() {
  local path="$1"
  case "$path" in
    "docs/REFERENCE/IMPROVEMENTS.md")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_requested_tooling_ref() {
  if [ "$USE_LOCAL_GIT" = true ]; then
    git -C "$TOOLING_DIR" rev-parse --verify "${TOOLING_VERSION}^{commit}" 2>/dev/null || true
  else
    echo ""
  fi
}

write_sync_lock() {
  local lock_path="$1"
  local target_root="$2"
  local requested_ref="$3"
  local resolved_ref="$4"
  local source_mode="$5"
  local tooling_repo="$6"
  shift 6

  if [ "$#" -eq 0 ]; then
    echo "ERROR: Cannot write sync lock with zero managed files." >&2
    return 1
  fi

  "$SYNC_PYTHON" - "$lock_path" "$target_root" "$requested_ref" "$resolved_ref" "$source_mode" "$tooling_repo" "$@" <<'PY'
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

lock_path = Path(sys.argv[1])
target_root = Path(sys.argv[2]).resolve()
requested_ref = sys.argv[3]
resolved_ref = sys.argv[4] or None
source_mode = sys.argv[5]
tooling_repo = sys.argv[6] or None
files = sorted(dict.fromkeys(sys.argv[7:]))

payload = {
    "schema_version": 1,
    "generated_at_utc": (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    ),
    "requested_ref": requested_ref,
    "resolved_ref": resolved_ref,
    "source_mode": source_mode,
    "files": {},
}

if tooling_repo is not None:
    payload["tooling_repo"] = tooling_repo

for rel_path in files:
    file_path = target_root / rel_path
    file_path_abs = Path(os.path.abspath(file_path))
    if file_path.is_symlink():
        print(
            f"ERROR: Cannot write sync lock because managed file is a symlink: {rel_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        resolved_path = file_path.resolve(strict=True)
    except FileNotFoundError:
        print(
            f"ERROR: Cannot write sync lock because managed file is missing: {rel_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        resolved_path.relative_to(target_root)
    except ValueError:
        print(
            f"ERROR: Cannot write sync lock because managed file escapes target root: {rel_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if resolved_path != file_path_abs:
        print(
            f"ERROR: Cannot write sync lock because managed file uses symlink traversal: {rel_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not resolved_path.is_file():
        print(
            f"ERROR: Cannot write sync lock because managed file is missing: {rel_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        file_bytes = resolved_path.read_bytes()
    except OSError as exc:
        print(
            f"ERROR: Cannot write sync lock because managed file cannot be read: {rel_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    digest = hashlib.sha256(file_bytes).hexdigest()
    payload["files"][rel_path] = {"sha256": digest}

# Refuse unsafe lock paths to avoid writing outside the repo or over non-regular files.
if lock_path.exists():
    if lock_path.is_symlink():
        print(
            f"ERROR: Refusing to write sync lock because lock path is a symlink: {lock_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not lock_path.is_file():
        print(
            f"ERROR: Refusing to write sync lock because lock path is not a regular file: {lock_path}",
            file=sys.stderr,
        )
        sys.exit(1)

lock_dir = lock_path.parent
lock_dir.mkdir(parents=True, exist_ok=True)
serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
with tempfile.NamedTemporaryFile(
    mode="w",
    encoding="utf-8",
    dir=str(lock_dir),
    delete=False,
) as tmp_file:
    tmp_file.write(serialized)
    tmp_path = Path(tmp_file.name)

try:
    os.replace(tmp_path, lock_path)
except OSError as exc:
    print(
        f"ERROR: Failed to write sync lock at {lock_path}: {exc}",
        file=sys.stderr,
    )
    try:
        tmp_path.unlink()
    except OSError:
        pass
    sys.exit(1)
PY
}

# Load sync allow-list from .tooling-sync-manifest.toml.
# Fails fast if the manifest is missing, unparseable, or has an empty file list.
MANIFEST_FILE="$TOOLING_DIR/.tooling-sync-manifest.toml"
if [ ! -f "$MANIFEST_FILE" ]; then
  echo "ERROR: Sync manifest not found: $MANIFEST_FILE"
  echo "Expected .tooling-sync-manifest.toml at the root of the tooling source."
  echo "See docs/REFERENCE/SYNC_MANIFEST.md for the file format."
  exit 1
fi
_sync_files_tmp=$(mktemp)
if ! "$SYNC_PYTHON" - "$MANIFEST_FILE" > "$_sync_files_tmp" <<'PY'
import sys
manifest_path = sys.argv[1]
try:
    import tomllib
except ImportError:
    print("ERROR: Python 3.11+ with tomllib is required to parse the sync manifest.", file=sys.stderr)
    sys.exit(1)
try:
    with open(manifest_path, "rb") as f:
        manifest = tomllib.load(f)
except Exception as e:
    print(f"ERROR: Failed to parse sync manifest {manifest_path}: {e}", file=sys.stderr)
    sys.exit(1)
files = manifest.get("sync", {}).get("files", [])
if not files:
    print(f"ERROR: Sync manifest has no entries in [sync].files: {manifest_path}", file=sys.stderr)
    sys.exit(1)
for entry in files:
    print(entry)
PY
then
  rm -f "$_sync_files_tmp"
  echo "ERROR: Failed to load sync manifest $MANIFEST_FILE"
  exit 1
fi
mapfile -t SYNC_FILES < "$_sync_files_tmp"
rm -f "$_sync_files_tmp"
# Fail fast if the manifest loaded zero files.
if [ "${#SYNC_FILES[@]}" -eq 0 ]; then
  echo "ERROR: Sync manifest loaded zero files from $MANIFEST_FILE"
  exit 1
fi

# Load previously managed file list from the prior lock (if present).
# Missing/invalid prior lock is treated as "no baseline" for deletion safety.
PRIOR_LOCK_FILE="$TARGET_DIR/.tooling-sync-manifest.lock"
PREVIOUS_MANAGED_FILES=()
if [ -f "$PRIOR_LOCK_FILE" ]; then
  _previous_files_tmp="$(mktemp)"
  if "$SYNC_PYTHON" - "$PRIOR_LOCK_FILE" > "$_previous_files_tmp" <<'PY'
import json
import sys

lock_path = sys.argv[1]
try:
    with open(lock_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
except Exception as exc:
    print(f"ERROR: Failed to parse prior sync lock {lock_path}: {exc}", file=sys.stderr)
    sys.exit(1)

files = payload.get("files", {})
if not isinstance(files, dict):
    print(
        f"ERROR: Prior sync lock has invalid 'files' object: {lock_path}",
        file=sys.stderr,
    )
    sys.exit(1)

for rel_path in files:
    print(rel_path)
PY
  then
    mapfile -t PREVIOUS_MANAGED_FILES < "$_previous_files_tmp"
  else
    echo "WARNING: Could not read prior lock file; skipping stale-file removal baseline: $PRIOR_LOCK_FILE"
  fi
  rm -f "$_previous_files_tmp"
fi
# Validate that every declared manifest entry exists in the tooling source.
# Uses git ls-tree for local-git mode (one fast call); filesystem stat for archive mode.
if [ "$USE_LOCAL_GIT" = true ]; then
  SYNC_SOURCE_MODE="git"
  RESOLVED_TOOLING_REF="$(resolve_requested_tooling_ref)"
  if [ -z "$RESOLVED_TOOLING_REF" ]; then
    echo "ERROR: Could not resolve tooling ref to an immutable commit: $TOOLING_VERSION"
    exit 1
  fi

  declare -A _GIT_FILES
  while IFS= read -r _f; do
    _GIT_FILES["$_f"]=1
  done < <(git -C "$TOOLING_DIR" ls-tree -r --name-only "$TOOLING_VERSION" 2>/dev/null)
  _manifest_ok=true
  for file in "${SYNC_FILES[@]}"; do
    if [ -z "${_GIT_FILES[$file]+_}" ]; then
      echo "ERROR: Manifest entry not found in tooling source at $TOOLING_VERSION: $file"
      _manifest_ok=false
    fi
  done
  unset _GIT_FILES
  if [ "$_manifest_ok" = false ]; then
    exit 1
  fi
elif [ "$USE_LOCAL_FILESYSTEM" = true ]; then
  SYNC_SOURCE_MODE="filesystem"
  RESOLVED_TOOLING_REF=""
  _manifest_ok=true
  for file in "${SYNC_FILES[@]}"; do
    if [ ! -f "$TOOLING_DIR/$file" ]; then
      echo "ERROR: Manifest entry not found in tooling source at $TOOLING_DIR: $file"
      _manifest_ok=false
    fi
  done
  if [ "$_manifest_ok" = false ]; then
    exit 1
  fi
else
  # GitHub mode not yet implemented - fail fast instead of silently syncing zero files
  echo "ERROR: GitHub sync mode is not yet implemented."
  echo "Please use local git or local archive sync by setting TOOLING_DIR"
  echo ""
  echo "To clone the tooling repository:"
  echo "  cd .."
  echo "  git clone https://github.com/jsmithpkp21/tooling.git"
  echo ""
  exit 1
fi

TOOLING_REPO_METADATA="${TOOLING_REPO:-}"
if [ -z "$TOOLING_REPO_METADATA" ] && [ "$USE_LOCAL_GIT" = true ]; then
  TOOLING_REPO_METADATA="$(git -C "$TOOLING_DIR" config --get remote.origin.url 2>/dev/null || echo "")"
fi

# Strip URL userinfo to avoid persisting tokens/credentials in lock metadata.
if [ -n "$TOOLING_REPO_METADATA" ]; then
  TOOLING_REPO_METADATA="$(printf '%s\n' "$TOOLING_REPO_METADATA" | sed -E 's#^(https?://)[^/@]*@#\1#')"
fi

# Track per-file sync failures so we do not emit a partial lock file.
SYNC_HAD_ERRORS=0
COPIED_FILES=()
for file in "${SYNC_FILES[@]}"; do
  echo "Syncing $file from tooling repo..."

  # SECURITY: Validate path before use to prevent directory traversal
  if ! validate_sync_path "$file"; then
    echo "SECURITY: Skipping unsafe path: $file"
    SYNC_HAD_ERRORS=1
    continue
  fi

  tmp_file="$(mktemp)"

  if [ "$USE_LOCAL_GIT" = true ]; then
    if ! git -C "$TOOLING_DIR" show "${RESOLVED_TOOLING_REF}:${file}" > "$tmp_file" 2>/dev/null; then
      echo "ERROR: $file not found in tooling repo at resolved ref $RESOLVED_TOOLING_REF (requested $TOOLING_VERSION)."
      rm -f "$tmp_file"
      SYNC_HAD_ERRORS=1
      continue
    fi
  else
    if [ ! -f "$TOOLING_DIR/$file" ]; then
      echo "ERROR: $file not found in tooling source at $TOOLING_DIR."
      rm -f "$tmp_file"
      SYNC_HAD_ERRORS=1
      continue
    fi
    cp "$TOOLING_DIR/$file" "$tmp_file"
  fi

  # Validate downloaded/checked-out file
  if head -5 "$tmp_file" | grep -q "^<!DOCTYPE html>"; then
    echo "ERROR: $file not updated. Response contains HTML (bad path or auth issue)."
    rm -f "$tmp_file"
    SYNC_HAD_ERRORS=1
    continue
  fi
  if [ ! -s "$tmp_file" ] && ! is_allowed_empty_file "$file"; then
    echo "ERROR: $file not updated. File is empty."
    rm -f "$tmp_file"
    SYNC_HAD_ERRORS=1
    continue
  fi

  # SECURITY: Verify no symlinks in destination path (prevents symlink traversal)
  if ! validate_no_symlink_traversal "$file"; then
    echo "SECURITY: Skipping file due to symlink in path: $file"
    rm -f "$tmp_file"
    SYNC_HAD_ERRORS=1
    continue
  fi

  # Create target directory and copy file
  mkdir -p "$(dirname "$TARGET_DIR/$file")"
  cp "$tmp_file" "$TARGET_DIR/$file"
  COPIED_FILES+=("$file")
  rm -f "$tmp_file"
  echo "✓ Done: $file"
done

# Fail immediately if any managed file failed to sync.
# This prevents post-sync steps (chmod, merge_pyproject, release-please config)
# from mutating files when the copy phase was incomplete.
if [ "$SYNC_HAD_ERRORS" -ne 0 ]; then
  echo "ERROR: One or more managed files failed to sync; aborting post-sync steps."
  exit 1
fi

# Safe deletion pass: remove files that were previously managed but are no
# longer present in the current manifest unless --no-delete is active.
if [ "${#PREVIOUS_MANAGED_FILES[@]}" -gt 0 ]; then
  declare -A _CURRENT_SYNC_SET
  for _current_path in "${SYNC_FILES[@]}"; do
    _CURRENT_SYNC_SET["$_current_path"]=1
  done

  for stale_file in "${PREVIOUS_MANAGED_FILES[@]}"; do
    if [ -n "${_CURRENT_SYNC_SET[$stale_file]+_}" ]; then
      continue
    fi

    if ! validate_sync_path "$stale_file"; then
      echo "SECURITY: Skipping stale file removal due to unsafe path: $stale_file"
      continue
    fi

    stale_target="$TARGET_DIR/$stale_file"

    if is_preserved_local_stale_file "$stale_file"; then
      if [ -L "$stale_target" ]; then
        echo "SECURITY: Preserved local stale target is symlink: $stale_file"
        continue
      fi
      if [ ! -e "$stale_target" ]; then
        continue
      fi
      if [ ! -f "$stale_target" ]; then
        echo "SECURITY: Preserved local stale target is not a regular file: $stale_file"
        continue
      fi
      echo "PRESERVED LOCAL: $stale_file"
      continue
    fi

    # Never delete through a symlink path.
    if [ -L "$stale_target" ]; then
      echo "SECURITY: Skipping stale file removal because target is symlink: $stale_file"
      continue
    fi

    if [ ! -e "$stale_target" ]; then
      continue
    fi

    if [ "$NO_DELETE" = true ]; then
      echo "SKIPPED REMOVAL (--no-delete): $stale_file"
      continue
    fi

    if ! validate_no_symlink_traversal "$stale_file" 2>/dev/null; then
      echo "SECURITY: Skipping stale file removal due to potential symlink traversal: $stale_file"
      continue
    fi

    if [ ! -f "$stale_target" ]; then
      echo "SECURITY: Skipping stale file removal because target is not a regular file: $stale_file"
      continue
    fi

    rm -f "$stale_target"
    echo "REMOVED: $stale_file"
  done

  unset _CURRENT_SYNC_SET
fi

# Shell scripts created from mktemp payloads can lose executable bits; normalize at end
# for files that were actually copied this run.
for file in "${COPIED_FILES[@]}"; do
  if [[ "$file" == *.sh ]] && [ -f "$TARGET_DIR/$file" ]; then
    chmod +x "$TARGET_DIR/$file"
  fi
done

# Generate pyproject.toml from project metadata + tooling configs
if [ -f "$TARGET_DIR/.pyproject.meta.toml" ]; then
  if [ -f "$TARGET_DIR/scripts/merge_pyproject.py" ]; then
    echo "Merging project metadata with tooling configs..."

    merge_args=("$TARGET_DIR/scripts/merge_pyproject.py" "$TARGET_DIR")
    if [ -n "${TOOLING_DIR:-}" ]; then
      merge_args+=(--tooling-dir "$TOOLING_DIR")
    fi

    if "$SYNC_PYTHON" "${merge_args[@]}"; then
      echo "✓ Generated pyproject.toml from metadata"
    else
      # When the consumer venv was successfully resolved the merge depends on
      # tomli_w being installed there; a failure is a real bug rather than a
      # missing dep, so refuse to mask it with a warning.
      if [ "$SYNC_PYTHON_FROM_VENV" = true ]; then
        echo "ERROR: Failed to generate pyproject.toml using consumer venv interpreter ($SYNC_PYTHON)."
        echo "       Inspect .pyproject.meta.toml and tooling/pyproject.toml for the underlying error."
        exit 1
      fi
      echo "⚠ Warning: Failed to generate pyproject.toml. Check .pyproject.meta.toml and tooling/pyproject.toml"
      echo "  No consumer venv was found at $TARGET_DIR_ABS/.venv or $SYNC_PYTHON_ENVS_CANDIDATE."
      echo "  Falling back to system python3, which may lack tomli_w. Run 'make setup' to provision the venv,"
      echo "  then re-run 'make sync-tooling' so the regeneration step runs under the consumer interpreter."
    fi
  fi
fi

# Update .release-please-config.json with project-specific package-name
if [ -f "$TARGET_DIR/.release-please-config.json" ] && [ -f "$TARGET_DIR/.pyproject.meta.toml" ]; then
  echo "Updating .release-please-config.json with project metadata..."
  RELEASE_CONFIG="$TARGET_DIR/.release-please-config.json"
  META_CONFIG="$TARGET_DIR/.pyproject.meta.toml"

  # Attempt update with Python (requires 3.11+ for tomllib)
  # If this fails, emit warning but don't abort entire sync
  if "$SYNC_PYTHON" << PYTHON_END
import json
import sys
try:
  import tomllib
except ImportError:
  print("⚠ Warning: Python 3.11+ required for tomllib (skipping .release-please-config.json update)", file=sys.stderr)
  sys.exit(1)

from pathlib import Path

config_path = Path("$RELEASE_CONFIG")
meta_path = Path("$META_CONFIG")

try:
  # Read project name from metadata
  with open(meta_path, "rb") as f:
    meta = tomllib.load(f)
  package_name = meta.get("project", {}).get("name", "")

  if not package_name:
    print("⚠ Warning: package name not found in .pyproject.meta.toml", file=sys.stderr)
    sys.exit(1)

  # Update config with package name
  with open(config_path) as f:
    config = json.load(f)

  config["packages"]["."]["package-name"] = package_name

  # Write back with proper formatting
  with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

  print(f"✓ Updated .release-please-config.json: package-name = {package_name}")
except Exception as e:
  print(f"⚠ Warning: Failed to update .release-please-config.json: {e}", file=sys.stderr)
  sys.exit(1)
PYTHON_END
  then
    : # Success - Python block updated config
  else
    if [ "$SYNC_PYTHON_FROM_VENV" = true ]; then
      echo "ERROR: Failed to update .release-please-config.json using consumer venv interpreter ($SYNC_PYTHON)."
      echo "       Inspect .pyproject.meta.toml and .release-please-config.json for the underlying error."
      exit 1
    fi
    echo "⚠ Warning: Could not update .release-please-config.json (Python 3.11+ or valid TOML required)"
    echo "  You may need to manually set 'package-name' in .release-please-config.json"
  fi
fi

LOCK_FILE="$TARGET_DIR/.tooling-sync-manifest.lock"
if ! write_sync_lock \
  "$LOCK_FILE" \
  "$TARGET_DIR" \
  "$TOOLING_VERSION" \
  "$RESOLVED_TOOLING_REF" \
  "$SYNC_SOURCE_MODE" \
  "$TOOLING_REPO_METADATA" \
  "${SYNC_FILES[@]}"; then
  echo "ERROR: Failed to write sync lock file: $LOCK_FILE"
  exit 1
fi

echo "✓ Wrote sync lock: $LOCK_FILE"

echo ""
echo "Sync completed successfully."
