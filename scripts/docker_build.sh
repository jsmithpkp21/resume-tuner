#!/usr/bin/env bash
set -euo pipefail

# Build Docker image using the same inputs as CI.
# This script reads versions from setup files and passes build args
# to ensure local builds match CI builds exactly.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# shellcheck disable=SC1091
source "$REPO_ROOT/scripts/load_build_env.sh"

IMAGE_TAG="base_repo:${ENV_VERSION}"

docker build \
  --build-arg PYTHON_VERSION="$PYTHON_VERSION" \
  --build-arg PIP_VERSION="$PIP_VERSION" \
  -t "$IMAGE_TAG" \
  "$REPO_ROOT"

echo "✅ Built Docker image: $IMAGE_TAG"
