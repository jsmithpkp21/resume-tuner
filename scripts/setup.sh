#!/usr/bin/env bash
# setup.sh — Bootstrap a new project from the project-template.
#
# Usage:
#   bash scripts/setup.sh              # Default/minimal setup
#   bash scripts/setup.sh playwright   # With Playwright layer
#   bash scripts/setup.sh api          # With API layer
#   bash scripts/setup.sh web          # With Web layer
#
# Environment variables:
#   TOOLING_REPO     GitHub URL of the tooling repo (default: https://github.com/jsmithpkp21/tooling)
#   TOOLING_VERSION  Tag/branch to sync from      (default: main)
#   GITHUB_TOKEN     Optional GitHub token for private repos
set -euo pipefail

LAYER="${1:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

TOOLING_REPO="${TOOLING_REPO:-https://github.com/jsmithpkp21/tooling}"
TOOLING_VERSION="${TOOLING_VERSION:-main}"

SUPPORTED_LAYERS=("playwright" "api" "web")

# ---------------------------------------------------------------------------
# Validate layer argument
# ---------------------------------------------------------------------------
if [ -n "$LAYER" ]; then
  valid=false
  for supported in "${SUPPORTED_LAYERS[@]}"; do
    if [ "$LAYER" = "$supported" ]; then
      valid=true
      break
    fi
  done
  if ! $valid; then
    echo "ERROR: Unknown layer '$LAYER'."
    echo "Supported layers: ${SUPPORTED_LAYERS[*]}"
    exit 1
  fi
fi

echo "======================================"
echo "  Project Setup"
if [ -n "$LAYER" ]; then
  echo "  Layer: $LAYER"
fi
echo "======================================"
echo ""

# ---------------------------------------------------------------------------
# 1. Obtain tooling repo archive and locate sync_tooling.sh
# ---------------------------------------------------------------------------
TOOLING_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/tooling-XXXXXX")"
trap 'rm -rf "$TOOLING_TMP_DIR"' EXIT

echo "Downloading tooling archive from $TOOLING_REPO ($TOOLING_VERSION)..."
ARCHIVE_BASE="${TOOLING_REPO//github.com/codeload.github.com}"
ARCHIVE_URL="${ARCHIVE_BASE}/tar.gz/${TOOLING_VERSION}"

CURL_ARGS=(-sSL -f)
if [ -n "${GITHUB_TOKEN:-}" ]; then
  CURL_CONFIG_FILE="${TOOLING_TMP_DIR}/curl_auth.conf"
  old_umask="$(umask)"
  umask 077
  printf 'header = "Authorization: token %s"\n' "${GITHUB_TOKEN}" > "${CURL_CONFIG_FILE}"
  umask "${old_umask}"
  CURL_ARGS+=(--config "${CURL_CONFIG_FILE}")
fi
if ! curl "${CURL_ARGS[@]}" \
     "$ARCHIVE_URL" \
     -o "${TOOLING_TMP_DIR}/tooling.tar.gz"; then
  echo "ERROR: Could not download tooling archive from $TOOLING_REPO."
  exit 1
fi

tar -xzf "${TOOLING_TMP_DIR}/tooling.tar.gz" -C "$TOOLING_TMP_DIR"
TOOLING_EXTRACT_DIR="$(find "$TOOLING_TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [ -z "${TOOLING_EXTRACT_DIR:-}" ] || [ ! -d "$TOOLING_EXTRACT_DIR" ]; then
  echo "ERROR: Failed to extract tooling archive."
  exit 1
fi

SYNC_SCRIPT="$TOOLING_EXTRACT_DIR/scripts/sync_tooling.sh"
if [ ! -f "$SYNC_SCRIPT" ]; then
  echo "ERROR: sync_tooling.sh not found in tooling archive."
  exit 1
fi
chmod +x "$SYNC_SCRIPT"
echo "✓ Tooling archive downloaded and sync_tooling.sh located"

# ---------------------------------------------------------------------------
# 2. Sync all tooling files into the project
# ---------------------------------------------------------------------------
echo ""
echo "Syncing tooling files from downloaded tooling archive ($TOOLING_VERSION)..."
TOOLING_DIR="$TOOLING_EXTRACT_DIR" bash "$SYNC_SCRIPT" "$TOOLING_VERSION" "$PROJECT_DIR"

# ---------------------------------------------------------------------------
# 3. Initialize git repository
# ---------------------------------------------------------------------------
echo ""
echo "Initializing git repository..."
if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$PROJECT_DIR" init
  echo "✓ Git repository initialized"
else
  echo "✓ Git repository already exists"
fi

# ---------------------------------------------------------------------------
# 4. Install git hooks (branch protection)
# ---------------------------------------------------------------------------
echo ""
echo "Installing git hooks..."
GIT_HOOKS_DIR="$(git -C "$PROJECT_DIR" rev-parse --git-path hooks 2>/dev/null || echo "$PROJECT_DIR/.git/hooks")"
if [ -d "$PROJECT_DIR/.githooks" ]; then
  mkdir -p "$GIT_HOOKS_DIR"
  for hook in "$PROJECT_DIR/.githooks/"*; do
    [ -f "$hook" ] || continue
    hook_name="$(basename "$hook")"
    cp "$hook" "$GIT_HOOKS_DIR/$hook_name"
    chmod +x "$GIT_HOOKS_DIR/$hook_name"
    echo "✓ Installed hook: $hook_name"
  done
elif [ -f "$PROJECT_DIR/Makefile" ] && grep -q "install-hooks" "$PROJECT_DIR/Makefile"; then
  make -C "$PROJECT_DIR" install-hooks
else
  echo "⚠️  No .githooks directory found; skipping hook installation"
fi

# ---------------------------------------------------------------------------
# 5. Configure chosen layer
# ---------------------------------------------------------------------------
if [ -n "$LAYER" ]; then
  echo ""
  echo "Configuring $LAYER layer..."
  case "$LAYER" in
    playwright)
      if [ -f "$PROJECT_DIR/scripts/prepare_playwright_layer.py" ]; then
        python3 "$PROJECT_DIR/scripts/prepare_playwright_layer.py"
        echo "✓ Playwright layer configured"
      else
        echo "⚠️  prepare_playwright_layer.py not found; Playwright layer skipped"
      fi
      ;;
    api)
      echo "✓ API layer selected"
      echo "  Add API-specific dependencies to requirements.txt as needed."
      ;;
    web)
      echo "✓ Web layer selected"
      echo "  Add web-specific dependencies to requirements.txt as needed."
      ;;
  esac
fi

# ---------------------------------------------------------------------------
# 6. Remove template-specific files
# ---------------------------------------------------------------------------
echo ""
echo "Cleaning up template files..."
# Remove this setup script — it is only needed once
rm -f "$SCRIPT_DIR/setup.sh"
echo "✓ setup.sh removed"

# ---------------------------------------------------------------------------
# 7. Display completion message
# ---------------------------------------------------------------------------
echo ""
echo "======================================"
echo "  Setup Complete!"
echo "======================================"
echo ""
echo "Your project is ready. Next steps:"
echo ""
echo "  1. Create the Python virtual environment:"
echo "       make env"
echo ""
echo "  2. Activate the environment:"
echo "       make active"
echo ""
echo "  3. Full setup (env + verify + hooks + pre-commit):"
echo "       make setup"
echo ""
if [ -n "$LAYER" ]; then
  echo "  Layer configured: $LAYER"
  echo ""
fi
echo "======================================"
