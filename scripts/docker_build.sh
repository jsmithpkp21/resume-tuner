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
# Validate the opt-in when set: unset or empty defaults to "0" (the safe
# default — refuse root); any other value is rejected fast rather than
# treated as truthy/falsy, so a typo like `HOST_UID_ALLOW_ROOT=true`
# doesn't silently bake root, and so the value is safe to forward as a
# `--build-arg` without quoting concerns. The `:-0` default matters
# here: callers that conditionally export the var (CI configs, wrapper
# scripts) commonly leave it as the empty string when "off", which
# should behave identically to unset.
case "${HOST_UID_ALLOW_ROOT:-0}" in
  0|1) ;;
  *)
    echo "ERROR: HOST_UID_ALLOW_ROOT must be '0' or '1' (or unset/empty for default '0'), got: '${HOST_UID_ALLOW_ROOT}'" >&2
    exit 1
    ;;
esac
# Refuse to bake root by default — defeats issue #322. Opt in via
# HOST_UID_ALLOW_ROOT=1 if you really mean it (e.g. CI image that
# genuinely needs UID 0 for some downstream task).
#
# An all-zeros `case` (rather than `[ "$HOST_UID" -eq 0 ]`) catches the
# same bypass set — `0`, `00`, `000`, … — that `getent`/`useradd`/Docker
# `USER` resolve to UID 0, while sidestepping `[ -eq ]`'s base-detection
# edge cases: `08` errors in some shells (invalid octal), and bash's
# `[ -eq ]` auto-detects `0xN` as hex. The `^[0-9]+$` validation above
# already guarantees pure digits, so the only ambiguity left is whether
# the digits represent zero or non-zero — which a literal-character
# `case` answers without invoking arithmetic.
case "$HOST_UID" in
  *[!0]*) ;;  # contains a non-zero digit → not UID 0, allow
  *)          # all zeros → UID 0 in every downstream consumer
    if [ "${HOST_UID_ALLOW_ROOT:-0}" != "1" ]; then
      echo "ERROR: refusing to bake UID 0 (root) into the image." >&2
      echo "Re-run as a non-root user, set HOST_UID=<your-uid>, or pass HOST_UID_ALLOW_ROOT=1 to opt in." >&2
      exit 1
    fi
    ;;
esac

# Forward HOST_UID_ALLOW_ROOT through to the Dockerfile so the in-image
# guard (issue #353) sees the same opt-in the script itself just gated on.
# Defaults to "0" when the env var is unset so the build-arg is always
# present and the Dockerfile guard's default-refuse path is exercised.
docker build \
  --build-arg PYTHON_VERSION="$PYTHON_VERSION" \
  --build-arg PIP_VERSION="$PIP_VERSION" \
  --build-arg HOST_UID="$HOST_UID" \
  --build-arg HOST_GID="$HOST_GID" \
  --build-arg HOST_UID_ALLOW_ROOT="${HOST_UID_ALLOW_ROOT:-0}" \
  -t "$IMAGE_TAG" \
  "$REPO_ROOT"

echo "✅ Built Docker image: $IMAGE_TAG (UID=${HOST_UID}, GID=${HOST_GID})"
