#!/usr/bin/env bash
set -euo pipefail

# Load pinned build inputs from setup files and derive ENV_VERSION from VERSION.
# Usage:
#   source scripts/load_build_env.sh

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$REPO_ROOT/pyproject.toml" ]; then
  echo "ERROR: pyproject.toml not found at $REPO_ROOT/pyproject.toml" >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/tooling.toml" ]; then
  echo "ERROR: tooling.toml not found at $REPO_ROOT/tooling.toml" >&2
  exit 1
fi

if [ ! -f "$REPO_ROOT/VERSION" ]; then
  echo "ERROR: VERSION file not found at $REPO_ROOT/VERSION" >&2
  exit 1
fi

eval "$(REPO_ROOT="$REPO_ROOT" python3 - <<'PY'
import os
import re
import tomllib
from pathlib import Path

root = Path(os.environ["REPO_ROOT"])

_version_lines = (root / "VERSION").read_text(encoding="utf-8").splitlines()
_version_first = _version_lines[0] if _version_lines else ""
version = _version_first.split("#", 1)[0].strip()
if not version:
    raise SystemExit("VERSION file is empty")

# Read Python version from tooling.toml (source of truth)
tooling = tomllib.loads((root / "tooling.toml").read_text(encoding="utf-8"))
py_ver = tooling.get("python", {}).get("version", "")

if not py_ver:
    raise SystemExit("Could not parse python version from tooling.toml")

# Clean version string (remove any prefix like ==, >=, etc)
py_ver = re.sub(r"^[^0-9]*", "", py_ver)

pip_ver = tooling["tooling"]["pip"]
if not pip_ver:
    raise SystemExit("pip version not found in tooling.toml")

print(f"ENV_VERSION={version}")
print(f"PYTHON_VERSION={py_ver}")
print(f"PIP_VERSION={pip_ver}")
PY
)"

export ENV_VERSION
export PYTHON_VERSION
export PIP_VERSION
