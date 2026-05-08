#!/usr/bin/env bash
set -euo pipefail

# Build Docker image using the same inputs as CI.
# This script reads versions from setup files and passes build args
# to ensure local builds match CI builds exactly.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/load_build_env.sh"

IMAGE_TAG="base_repo:${ENV_VERSION}"

HOST_UID="${HOST_UID:-$(id -u)}"
HOST_GID="${HOST_GID:-$(id -g)}"

# Validate IDs are non-empty digits before passing to `docker build`.
# A misconfigured override (typo, empty string, non-numeric) would
# otherwise produce a cryptic Dockerfile failure deep inside the
# `useradd` / `groupadd` / `chown` step instead of failing fast here.
if ! [[ "$HOST_UID" =~ ^[0-9]+$ ]]; then
  echo "ERROR: HOST_UID must be a non-negative integer, got: '$HOST_UID'" >&2
  exit 1
fi
if ! [[ "$HOST_GID" =~ ^[0-9]+$ ]]; then
  echo "ERROR: HOST_GID must be a non-negative integer, got: '$HOST_GID'" >&2
  exit 1
fi
# Refuse to bake root by default — defeats issue #322. Opt in via
# HOST_UID_ALLOW_ROOT=1 if you really mean it (e.g. CI image that
# genuinely needs UID 0 for some downstream task).
if [ "$HOST_UID" = "0" ] && [ "${HOST_UID_ALLOW_ROOT:-0}" != "1" ]; then
  echo "ERROR: refusing to bake UID 0 (root) into the image." >&2
  echo "Re-run as a non-root user, set HOST_UID=<your-uid>, or pass HOST_UID_ALLOW_ROOT=1 to opt in." >&2
  exit 1
fi

docker build \
  --build-arg PYTHON_VERSION="$PYTHON_VERSION" \
  --build-arg PIP_VERSION="$PIP_VERSION" \
  --build-arg HOST_UID="$HOST_UID" \
  --build-arg HOST_GID="$HOST_GID" \
  -t "$IMAGE_TAG" \
  "$REPO_ROOT"

echo "✅ Built Docker image: $IMAGE_TAG (UID=${HOST_UID}, GID=${HOST_GID})"
