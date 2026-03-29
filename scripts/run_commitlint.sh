#!/usr/bin/env bash
# run_commitlint.sh — run commitlint against a commit message file.
#
# Runtime resolution order:
#   1. Local npm (present inside the project container — preferred path)
#   2. Docker with pinned @commitlint packages (host fallback)
#   3. Hard fail with actionable instructions if fallback runtime is unavailable
#
# Usage: bash scripts/run_commitlint.sh <commit-msg-file>
set -euo pipefail

COMMITLINT_VERSION="19.8.0"
INSTALL_FAIL_RC=125

if [[ $# -lt 1 ]]; then
  echo "ERROR: commit message file path must be provided as the first argument." >&2
  exit 1
fi

MSGFILE="$1"

if [[ ! -r "$MSGFILE" ]]; then
  echo "ERROR: commit message file '$MSGFILE' does not exist or is not readable." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="$REPO_ROOT/commitlint.config.mjs"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: commitlint config not found at $CONFIG" >&2
  exit 1
fi

# Resolve absolute path to message file (needed for Docker bind-mount)
ABS_MSGFILE="$(cd "$(dirname "$MSGFILE")" && pwd)/$(basename "$MSGFILE")"

# commitlint resolves `extends` relative to the cwd. Install once into a stable
# cache path keyed by version to avoid reinstalling on every commit-msg hook run.
_run_with_local_npm() {
  local cache_base cache_dir commitlint_bin install_log local_rc
  cache_base="${XDG_CACHE_HOME:-$HOME/.cache}"
  cache_dir="$cache_base/tooling-commitlint/$COMMITLINT_VERSION"
  commitlint_bin="$cache_dir/node_modules/.bin/commitlint"

  mkdir -p "$cache_dir"

  if [[ ! -x "$commitlint_bin" ]]; then
    install_log="$(mktemp)"
    if ! NPM_CONFIG_LOGLEVEL=silent NPM_CONFIG_UPDATE_NOTIFIER=false \
      npm install --prefix "$cache_dir" --no-save --ignore-scripts --no-audit --no-fund \
        "@commitlint/cli@$COMMITLINT_VERSION" \
        "@commitlint/config-conventional@$COMMITLINT_VERSION" \
        >"$install_log" 2>&1; then
      echo "commitlint: failed to install local npm runtime; trying Docker fallback" >&2
      cat "$install_log" >&2
      rm -f "$install_log"
      return "$INSTALL_FAIL_RC"
    fi
    rm -f "$install_log"
  fi

  set +e
  NODE_PATH="$cache_dir/node_modules" \
    "$commitlint_bin" \
      --config "$CONFIG" \
      --edit "$ABS_MSGFILE"
  local_rc=$?
  set -e

  if [[ "$local_rc" -ne 0 ]]; then
    # Commitlint executed and rejected the message. Do not fall back to Docker.
    return "$local_rc"
  fi

  return 0
}

_run_with_docker() {
  docker run --rm \
    -e NPM_CONFIG_LOGLEVEL=silent \
    -e NPM_CONFIG_UPDATE_NOTIFIER=false \
    -v "$REPO_ROOT":/repo \
    -v "$ABS_MSGFILE":/tmp/commit_editmsg_check \
    -w /tmp \
    node:20-bullseye \
    sh -lc "
      npm install --no-save --ignore-scripts --no-audit --no-fund \
        '@commitlint/cli@$COMMITLINT_VERSION' \
        '@commitlint/config-conventional@$COMMITLINT_VERSION' \
        >/tmp/commitlint-npm-install.log 2>&1 || {
          echo 'commitlint: Docker fallback failed to install runtime' >&2
          cat /tmp/commitlint-npm-install.log >&2
          exit 1
        }
      NODE_PATH=/tmp/node_modules \
        /tmp/node_modules/.bin/commitlint \
          --config /repo/commitlint.config.mjs \
          --edit /tmp/commit_editmsg_check
    "
}

if command -v npm >/dev/null 2>&1; then
  # Capture status explicitly; `if ...; then` masks the original non-zero code.
  set +e
  _run_with_local_npm
  local_rc=$?
  set -e

  if [[ "$local_rc" -eq 0 ]]; then
    exit 0
  fi

  if [[ "$local_rc" -ne "$INSTALL_FAIL_RC" ]]; then
    # Local commitlint ran and returned its actual validation result.
    exit "$local_rc"
  fi
  # Otherwise local runtime setup failed; try Docker fallback below.
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "commitlint: npm runtime unavailable and Docker is unavailable" >&2
  echo "Either run inside the project container (docker-compose up) or install Docker Desktop" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "commitlint: npm runtime unavailable and Docker daemon is not running" >&2
  echo "Start Docker Desktop. If using WSL2, enable Docker Desktop WSL integration for this distro" >&2
  exit 1
fi

_run_with_docker
