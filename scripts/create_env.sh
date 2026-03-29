#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------
# Deterministic environment creation script
# Reads Python version from pyproject.toml
# Reads pip version from tooling.toml
#
# Usage:
#   scripts/create_env.sh          # Create or skip if exists (idempotent)
#   scripts/create_env.sh --force  # Force recreation
# -----------------------------------------

# Error handler function (must be defined before trap)
on_error() {
    local line_number=$?
    if [ $line_number -ne 0 ]; then
        echo "ERROR: Script failed at line $line_number"
        if [ -d "$ENV_PATH" ] && [ ! -f "$ENV_PATH/bin/activate" ]; then
            echo "Cleaning up incomplete environment at $ENV_PATH"
            rm -rf "$ENV_PATH"
        fi
    fi
}

# Trap errors for cleanup
trap 'on_error' ERR EXIT

# Resolve repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Parse arguments
FORCE_RECREATE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --force) FORCE_RECREATE=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# -----------------------------------------
# Runtime contract checks (shell tooling)
# -----------------------------------------
REQUIRED_RUNTIME_TOOLS=(bash awk grep sed)
for tool in "${REQUIRED_RUNTIME_TOOLS[@]}"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "ERROR: Required runtime tool not found: $tool"
        exit 1
    fi
done

# Enforce awk implementation to avoid cross-platform parser drift.
if ! awk --version 2>/dev/null | grep -q "GNU Awk"; then
    echo "ERROR: awk implementation must be GNU Awk (gawk) per runtime contract"
    echo "Found: $(awk -W version 2>/dev/null | head -1 || echo 'unknown awk')"
    exit 1
fi

# -----------------------------------------
# Pre-flight checks
# -----------------------------------------

# Check that all required metadata files exist
for file in VERSION pyproject.toml tooling.toml requirements.txt; do
    if [ ! -f "$REPO_ROOT/$file" ]; then
        echo "ERROR: Required file not found: $REPO_ROOT/$file"
        exit 1
    fi
done

# Read environment version
if ! VERSION="$(cat "$REPO_ROOT/VERSION" 2>/dev/null)"; then
    echo "ERROR: Could not read VERSION file"
    exit 1
fi

if [ -z "$VERSION" ]; then
    echo "ERROR: VERSION file is empty"
    exit 1
fi

# Read pip version from tooling.toml with better error handling
if ! PIP_VERSION="$(grep -E '^pip' "$REPO_ROOT/tooling.toml" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; then
    echo "ERROR: Could not parse pip version from tooling.toml"
    exit 1
fi

if [ -z "$PIP_VERSION" ]; then
    echo "ERROR: pip version not found in tooling.toml"
    exit 1
fi

# -----------------------------------------
# Extract required Python version from tooling.toml [python] section
# (DRY layout - source of truth)
# Use simple grep + sed (POSIX tools) to avoid Python version dependencies
# -----------------------------------------

# Parse [python] section from tooling.toml
# Use awk stateful parser to properly handle section boundaries
# (sed range /start/,/end/ matches /start/ and /end/ on same line, causing immediate termination)
EXPECTED_PY_VERSION=""
PY_VERSION_SOURCE=""
if [ -f "$REPO_ROOT/tooling.toml" ]; then
    # Extract version from [python] section using awk (POSIX tools, no Python dependency)
    # awk tracks state: in_python=1 inside [python] section, stops at next [section]
    EXPECTED_PY_VERSION="$(awk '
      /^[[:space:]]*\[python\]/ {
        in_python = 1
        next
      }
      /^[[:space:]]*\[/ {
        in_python = 0
      }
      in_python && /^[[:space:]]*version[[:space:]]*=/ {
        # Extract quoted value: version = "3.11" -> 3.11
        sub(/.*version[[:space:]]*=[[:space:]]*"/, "")
        sub(/".*/, "")
        print
        exit
      }
    ' "$REPO_ROOT/tooling.toml")"
    if [ -n "$EXPECTED_PY_VERSION" ]; then
        PY_VERSION_SOURCE="tooling.toml"
    fi
fi

# Fallback to pyproject.toml if tooling.toml doesn't have [python].version
if [ -z "$EXPECTED_PY_VERSION" ]; then
    REQUIRES_LINE="$(grep -E 'requires-python' "$REPO_ROOT/pyproject.toml" || true)"
    EXPECTED_PY_VERSION="$(echo "$REQUIRES_LINE" | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    if [ -n "$EXPECTED_PY_VERSION" ]; then
        PY_VERSION_SOURCE="pyproject.toml"
    fi
fi

if [ -z "$EXPECTED_PY_VERSION" ]; then
    echo "ERROR: Could not parse Python version from tooling.toml or pyproject.toml"
    echo "Please ensure tooling.toml has: [python] section with version = \"X.Y\""
    exit 1
fi

echo "Expected Python version from $PY_VERSION_SOURCE: $EXPECTED_PY_VERSION"

# -----------------------------------------
# Select Python interpreter dynamically
# -----------------------------------------

PY_MAJOR="$(echo "$EXPECTED_PY_VERSION" | cut -d. -f1)"
PY_MINOR="$(echo "$EXPECTED_PY_VERSION" | cut -d. -f2)"
PY_INTERPRETER="python${PY_MAJOR}.${PY_MINOR}"

if command -v "$PY_INTERPRETER" >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v "$PY_INTERPRETER")"
else
    echo "ERROR: Required interpreter $PY_INTERPRETER not found."
    echo "Install it with:"
    echo "  sudo apt install ${PY_INTERPRETER} ${PY_INTERPRETER}-venv ${PY_INTERPRETER}-dev"
    exit 1
fi

# Verify interpreter version (major.minor only, since apt-installed python3.11 reports 3.11 not 3.11.14)
ACTUAL_PY_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)" || {
    echo "ERROR: Could not determine Python version for $PYTHON_BIN"
    exit 1
}

# Extract major.minor from expected version for comparison (3.11.14 → 3.11)
EXPECTED_PY_MAJOR_MINOR="$(echo "$EXPECTED_PY_VERSION" | cut -d. -f1-2)"

if [ "$ACTUAL_PY_VERSION" != "$EXPECTED_PY_MAJOR_MINOR" ]; then
    echo "ERROR: Python version mismatch"
    echo "Expected: $EXPECTED_PY_MAJOR_MINOR (from $EXPECTED_PY_VERSION)"
    echo "Found:    $ACTUAL_PY_VERSION"
    exit 1
fi

echo "Using Python interpreter: $PYTHON_BIN (version $ACTUAL_PY_VERSION)"

# -----------------------------------------
# Environment directory
# -----------------------------------------

# Detect repository name from git remote or directory name
# This allows the same script to work across different repos with unique venv names
REPO_NAME=""
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Try to extract repo name from git remote origin URL
  # Examples:
  #   git@github.com:user/tooling.git -> tooling
  #   https://github.com/github-user/base_repo.git -> base_repo
  REPO_NAME=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null | sed 's|.*[/:]||; s|\.git$||' || true)
fi

# Fallback to directory name if git remote not found
if [ -z "$REPO_NAME" ]; then
  REPO_NAME="$(basename "$REPO_ROOT")"
fi

ENV_ROOT="$HOME/envs"
ENV_NAME="${REPO_NAME}-env"
ENV_PATH="$ENV_ROOT/$ENV_NAME"

echo "-----------------------------------------"
echo " Creating deterministic environment"
echo " Version: $VERSION"
echo " Expected Python: $EXPECTED_PY_VERSION"
echo " Expected pip:    $PIP_VERSION"
echo " Location:        $ENV_PATH"
echo "-----------------------------------------"

mkdir -p "$ENV_ROOT"

# Check if environment already exists
if [ -d "$ENV_PATH" ]; then
    if [ "$FORCE_RECREATE" = true ]; then
        echo "Environment exists, but --force specified. Removing..."
        rm -rf "$ENV_PATH"
    else
        echo "Environment already exists at $ENV_PATH"
        echo "Skipping creation (idempotent behavior)"
        echo "Use --force to recreate"
        exit 0
    fi
fi

# -----------------------------------------
# Create virtual environment
# -----------------------------------------

echo "Creating virtual environment..."
if ! "$PYTHON_BIN" -m venv "$ENV_PATH"; then
    echo "ERROR: Failed to create virtual environment at $ENV_PATH"
    rm -rf "$ENV_PATH"
    exit 1
fi

# Activate environment
# shellcheck disable=SC1091
if ! source "$ENV_PATH/bin/activate"; then
    echo "ERROR: Failed to activate environment at $ENV_PATH"
    rm -rf "$ENV_PATH"
    exit 1
fi

# -----------------------------------------
# Install deterministic pip version
# -----------------------------------------

echo "Upgrading pip to $PIP_VERSION..."
if ! pip install --upgrade --quiet "pip==$PIP_VERSION"; then
    echo "ERROR: Failed to install pip==$PIP_VERSION"
    rm -rf "$ENV_PATH"
    exit 1
fi

# Verify pip installation
ACTUAL_PIP_VERSION="$(pip --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
if [ "$ACTUAL_PIP_VERSION" != "$PIP_VERSION" ]; then
    echo "ERROR: pip version mismatch after installation"
    echo "Expected: $PIP_VERSION"
    echo "Got:      $ACTUAL_PIP_VERSION"
    rm -rf "$ENV_PATH"
    exit 1
fi

echo "pip version OK: $ACTUAL_PIP_VERSION"

# -----------------------------------------
# Validate requirements.txt
# -----------------------------------------

if [ ! -f "$REPO_ROOT/requirements.txt" ]; then
    echo "ERROR: requirements.txt not found at $REPO_ROOT/requirements.txt"
    rm -rf "$ENV_PATH"
    exit 1
fi

REQ_LINE_COUNT=$(grep -v '^#' "$REPO_ROOT/requirements.txt" | grep -v '^$' | wc -l)
if [ "$REQ_LINE_COUNT" -eq 0 ]; then
    echo "ERROR: requirements.txt is empty or contains only comments"
    rm -rf "$ENV_PATH"
    exit 1
fi

echo "Installing requirements ($REQ_LINE_COUNT packages)..."

# -----------------------------------------
# Install project requirements with validation
# -----------------------------------------

if ! pip install --quiet -r "$REPO_ROOT/requirements.txt"; then
    echo "ERROR: Failed to install requirements from requirements.txt"
    rm -rf "$ENV_PATH"
    exit 1
fi

# Verify all packages are installed
echo "Verifying installation..."
if ! pip check --quiet; then
    echo "WARNING: pip check found some issues (may be non-critical)"
    pip check || true
fi

echo "-----------------------------------------"
echo " Environment created successfully!"
echo " Location:        $ENV_PATH"
echo " To activate:"
echo "   source $ENV_PATH/bin/activate"
echo "-----------------------------------------"
