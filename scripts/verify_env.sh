#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------
# Deterministic environment verification script
# Validates that the active environment matches repository contract
# -----------------------------------------

# Resolve repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Detect repository name from git remote or directory name
# This allows the same script to work across different repos with unique venv names
REPO_NAME=""
if git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Try to extract repo name from git remote origin URL
  # Examples:
  #   git@github.com:user/tooling.git -> tooling
  #   https://github.com/user/base_repo.git -> base_repo
  REPO_NAME=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null | sed 's|.*/||; s|.*:||; s|\.git$||' || true)
fi

# Fallback to directory name if git remote not found
if [ -z "$REPO_NAME" ]; then
  REPO_NAME="$(basename "$REPO_ROOT")"
fi

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

if ! awk --version 2>/dev/null | grep -q "GNU Awk"; then
    echo "ERROR: awk implementation must be GNU Awk (gawk) per runtime contract"
    echo "Found: $(awk -W version 2>/dev/null | head -1 || echo 'unknown awk')"
    exit 1
fi

# -----------------------------------------
# Pre-flight checks
# -----------------------------------------

# Check that all required metadata files exist
for file in VERSION pyproject.toml tooling.toml requirements.txt requirements-dev.txt; do
    if [ ! -f "$REPO_ROOT/$file" ]; then
        echo "ERROR: Required file not found: $REPO_ROOT/$file"
        exit 1
    fi
done

# Read expected environment version. Strip optional `# x-release-please-version`
# annotation (release-please needs the annotation in-file to bump VERSION; see
# issue #272).
if ! EXPECTED_VERSION="$(awk 'NR==1 {sub(/[[:space:]]*#.*$/, ""); gsub(/[[:space:]]/, ""); print; exit}' "$REPO_ROOT/VERSION" 2>/dev/null)"; then
    echo "ERROR: Could not read VERSION file"
    exit 1
fi

# Read pip version from tooling.toml
if ! EXPECTED_PIP_VERSION="$(grep -E '^pip' "$REPO_ROOT/tooling.toml" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"; then
    echo "ERROR: Could not parse pip version from tooling.toml"
    exit 1
fi

# Extract required Python version from tooling.toml [python] section (DRY layout - source of truth)
# Use awk stateful parser (consistent with create_env.sh) to avoid Python 3.11+ dependency
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

if [ -z "$EXPECTED_PY_VERSION" ]; then
    # Fallback: try pyproject.toml for repos that still have [project]
    REQUIRES_LINE="$(grep -E 'requires-python' "$REPO_ROOT/pyproject.toml" || true)"
    EXPECTED_PY_VERSION="$(echo "$REQUIRES_LINE" | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    if [ -n "$EXPECTED_PY_VERSION" ]; then
        PY_VERSION_SOURCE="pyproject.toml"
    fi
fi

if [ -z "$EXPECTED_PY_VERSION" ]; then
    echo "ERROR: Could not parse Python version from tooling.toml or pyproject.toml"
    exit 1
fi

echo "-----------------------------------------"
echo " Verifying deterministic environment"
echo " Expected environment version: $EXPECTED_VERSION"
echo " Expected Python version:      $EXPECTED_PY_VERSION"
echo " Expected pip version:         $EXPECTED_PIP_VERSION"
echo "-----------------------------------------"

# Ensure environment is activated
if [ -z "${VIRTUAL_ENV:-}" ]; then
    echo "ERROR: No virtual environment is active."
    echo "Please activate your environment first:"
    echo "  source ~/envs/${REPO_NAME}-env/bin/activate"
    exit 1
fi

echo "Active environment: $VIRTUAL_ENV"

# -----------------------------------------
# Verify Python version
# -----------------------------------------

# Match the precision pinned in tooling.toml: full M.m.p ⇒ strict patch
# compare, M.m ⇒ loose. See docs/REFERENCE/PYPROJECT_ARCHITECTURE.md.
case "$EXPECTED_PY_VERSION" in
    *.*.*) PY_VERSION_FORMAT='{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}' ;;
    *)     PY_VERSION_FORMAT='{sys.version_info.major}.{sys.version_info.minor}' ;;
esac

ACTUAL_PY_VERSION="$(python3 -c "import sys; print(f'$PY_VERSION_FORMAT')" 2>/dev/null)" || {
    echo "ERROR: Could not determine Python version"
    exit 1
}

if [ "$ACTUAL_PY_VERSION" != "$EXPECTED_PY_VERSION" ]; then
    echo "ERROR: Python version mismatch"
    echo "Expected: $EXPECTED_PY_VERSION (from $PY_VERSION_SOURCE)"
    echo "Found:    $ACTUAL_PY_VERSION (from active venv)"
    case "$EXPECTED_PY_VERSION" in
        *.*.*)
            echo
            echo "The consumer pinned a strict patch version. Recreate the venv with the"
            echo "exact interpreter (pyenv install $EXPECTED_PY_VERSION) or run via Docker."
            ;;
    esac
    exit 1
fi

echo "✓ Python version OK: $ACTUAL_PY_VERSION"

# -----------------------------------------
# Verify pip version
# -----------------------------------------

PIP_VERSION_OUTPUT="$(pip --version 2>/dev/null)" || {
    echo "ERROR: Could not determine pip version"
    exit 1
}

# Extract version using regex (handles different pip version output formats)
ACTUAL_PIP_VERSION="$(echo "$PIP_VERSION_OUTPUT" | grep -oE 'pip [0-9]+\.[0-9]+\.[0-9]+' | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || true)"

if [ -z "$ACTUAL_PIP_VERSION" ]; then
    echo "ERROR: Could not parse pip version from: $PIP_VERSION_OUTPUT"
    exit 1
fi

if [ "$ACTUAL_PIP_VERSION" != "$EXPECTED_PIP_VERSION" ]; then
    echo "ERROR: pip version mismatch"
    echo "Expected: $EXPECTED_PIP_VERSION"
    echo "Found:    $ACTUAL_PIP_VERSION"
    exit 1
fi

echo "✓ pip version OK: $ACTUAL_PIP_VERSION"

# -----------------------------------------
# Verify required tools are installed
# -----------------------------------------

echo "Checking installed tools..."

REQUIRED_TOOLS=(
    black
    isort
    ruff
    mypy
    pytest
    pre-commit
)

MISSING_TOOLS=()
for tool in "${REQUIRED_TOOLS[@]}"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        MISSING_TOOLS+=("$tool")
    fi
done

if [ ${#MISSING_TOOLS[@]} -gt 0 ]; then
    echo "ERROR: Missing required tools: ${MISSING_TOOLS[*]}"
    exit 1
fi

echo "✓ All required tools are installed"

# -----------------------------------------
# Verify some key packages are installed
# -----------------------------------------

echo "Checking key packages..."

# Sample check: a few packages from requirements.txt
SAMPLE_PACKAGES=(
    pytest
    ruff
    black
)

for package in "${SAMPLE_PACKAGES[@]}"; do
    if ! pip show "$package" >/dev/null 2>&1; then
        echo "ERROR: Package not found in environment: $package"
        exit 1
    fi
done

echo "✓ Key packages are installed"

echo "-----------------------------------------"
echo " Environment verification PASSED ✓"
echo "-----------------------------------------"
