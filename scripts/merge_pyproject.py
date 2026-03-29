#!/usr/bin/env python3
"""Merge project metadata with shared tooling configs to generate pyproject.toml.

This script combines:
1. tooling/pyproject.toml - shared tool configurations
2. .pyproject.meta.toml - project-specific metadata

Into a final pyproject.toml with both [build-system], [project], and [tool.*] sections.

Usage:
    python3 scripts/merge_pyproject.py [TARGET_DIR] [--tooling-dir TOOLING_DIR]

If TARGET_DIR is omitted, uses current directory.
The tooling directory is resolved in this order:
  1. --tooling-dir command-line argument
  2. TOOLING_DIR environment variable
  3. ../tooling sibling directory relative to the project
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override dict into base dict.

    Override values take precedence. Nested dicts are merged, not replaced.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def find_tooling_dir(start_path: Path) -> Path | None:
    """Find tooling repository relative to project.

    Resolution order:
    1. TOOLING_DIR environment variable
    2. ../tooling sibling directory relative to the project
    """
    env_tooling_dir = os.environ.get("TOOLING_DIR")
    if env_tooling_dir:
        candidate = Path(env_tooling_dir).expanduser().resolve()
        if candidate.is_dir():
            return candidate
        else:
            print(
                f"Warning: TOOLING_DIR is set to '{candidate}', which is not an existing directory. "
                "Falling back to sibling tooling directory resolution.",
                file=sys.stderr,
            )

    sibling_tooling = start_path.parent / "tooling"
    if sibling_tooling.is_dir():
        return sibling_tooling

    return None


def merge_pyproject(
    target_dir: Path | None = None, tooling_dir: Path | None = None
) -> bool:
    """Merge project metadata with tooling configs and write pyproject.toml.

    Args:
        target_dir: Project directory containing .pyproject.meta.toml.
                    Defaults to the current working directory.
        tooling_dir: Explicit path to the tooling repository.  When provided,
                     takes precedence over the TOOLING_DIR environment variable
                     and the ../tooling sibling heuristic.

    Returns True if successful, False otherwise.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    else:
        target_dir = Path(target_dir).resolve()

    # Paths
    meta_file = target_dir / ".pyproject.meta.toml"
    pyproject_file = target_dir / "pyproject.toml"

    # Step 1: Load project metadata
    if not meta_file.exists():
        print(f"❌ Error: {meta_file} not found.", file=sys.stderr)
        print(
            "Please create .pyproject.meta.toml with [project] section.",
            file=sys.stderr,
        )
        return False

    try:
        with open(meta_file, "rb") as f:
            meta_data = tomllib.load(f)
    except Exception as e:
        print(f"❌ Error reading {meta_file}: {e}", file=sys.stderr)
        return False

    if "project" not in meta_data:
        print(f"❌ Error: {meta_file} missing [project] section.", file=sys.stderr)
        return False

    # Step 2: Find and load tooling configs
    resolved_tooling_dir: Path
    if tooling_dir is not None:
        resolved_tooling_dir = Path(tooling_dir).expanduser().resolve()
        if not resolved_tooling_dir.is_dir():
            print(
                f"❌ Error: --tooling-dir path is not a valid directory: {resolved_tooling_dir}",
                file=sys.stderr,
            )
            return False
    else:
        found = find_tooling_dir(target_dir)
        if not found:
            print(
                "❌ Error: Could not find tooling repository.",
                file=sys.stderr,
            )
            print(
                "Set the TOOLING_DIR environment variable, use --tooling-dir, "
                "or place the tooling repo at ../tooling relative to the project.",
                file=sys.stderr,
            )
            return False
        resolved_tooling_dir = found

    tooling_pyproject = resolved_tooling_dir / "pyproject.toml"
    if not tooling_pyproject.exists():
        print(f"❌ Error: {tooling_pyproject} not found.", file=sys.stderr)
        return False

    try:
        with open(tooling_pyproject, "rb") as f:
            tooling_data = tomllib.load(f)
    except Exception as e:
        print(f"❌ Error reading {tooling_pyproject}: {e}", file=sys.stderr)
        return False

    # Step 3: Load project tooling.toml for Python version (single source of truth)
    tooling_toml = target_dir / "tooling.toml"
    python_version = None
    if tooling_toml.exists():
        try:
            with open(tooling_toml, "rb") as f:
                tooling_toml_data = tomllib.load(f)
                python_version = tooling_toml_data.get("python", {}).get("version")
        except Exception as e:
            print(
                f"⚠️  Warning: Could not read Python version from {tooling_toml}: {e}",
                file=sys.stderr,
            )

    # Step 4: Build final pyproject.toml
    final_pyproject: dict[str, Any] = {}

    # Add build-system (from tooling)
    if "build-system" in tooling_data:
        final_pyproject["build-system"] = tooling_data["build-system"]

    # Add project metadata
    final_pyproject["project"] = meta_data["project"].copy()

    # Inject requires-python from tooling.toml (single source of truth)
    if python_version:
        # Format with == for exact pinning
        if "." in python_version and python_version.count(".") >= 2:
            # Full version like "3.11.14"
            final_pyproject["project"]["requires-python"] = f"=={python_version}"
        else:
            # Major.minor like "3.11" - keep as-is for compatibility
            final_pyproject["project"]["requires-python"] = f">={python_version}"

    # Add tool configs (merge: tooling base + project overrides)
    tool_sections = {k: v for k, v in tooling_data.items() if k.startswith("tool")}
    for section_name, section_config in tool_sections.items():
        if section_name in meta_data:
            # Merge project-specific tool overrides
            final_pyproject[section_name] = deep_merge(
                section_config, meta_data[section_name]
            )
        else:
            final_pyproject[section_name] = section_config

    # Keep Ruff isort first-party package aligned with an importable project module name.
    project_name = str(meta_data.get("project", {}).get("name", "")).strip()
    first_party_name = project_name.replace("-", "_")
    if first_party_name and first_party_name.isidentifier():
        tool_cfg = final_pyproject.setdefault("tool", {})
        if not isinstance(tool_cfg, dict):
            tool_cfg = {}
            final_pyproject["tool"] = tool_cfg

        ruff_cfg = tool_cfg.setdefault("ruff", {})
        if not isinstance(ruff_cfg, dict):
            ruff_cfg = {}
            tool_cfg["ruff"] = ruff_cfg

        lint_cfg = ruff_cfg.setdefault("lint", {})
        if not isinstance(lint_cfg, dict):
            lint_cfg = {}
            ruff_cfg["lint"] = lint_cfg

        isort_cfg = lint_cfg.setdefault("isort", {})
        if not isinstance(isort_cfg, dict):
            isort_cfg = {}
            lint_cfg["isort"] = isort_cfg

        isort_cfg["known-first-party"] = [first_party_name]

    # Step 5: Write final pyproject.toml
    try:
        import tomli_w

        content = tomli_w.dumps(final_pyproject)
        with open(pyproject_file, "w") as f:
            f.write(content)
        print(f"✓ Generated {pyproject_file}")
        return True
    except ImportError:
        print("❌ Error: tomli_w not installed", file=sys.stderr)
        print("Install it with: pip install tomli_w", file=sys.stderr)
        return False
    except Exception as e:
        print(f"❌ Error writing {pyproject_file}: {e}", file=sys.stderr)
        return False


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Merge project metadata with shared tooling configs to generate pyproject.toml."
    )
    parser.add_argument(
        "target_dir",
        nargs="?",
        type=Path,
        default=None,
        help="Target project directory (default: current directory)",
    )
    parser.add_argument(
        "--tooling-dir",
        type=Path,
        default=None,
        help="Path to tooling repository (overrides TOOLING_DIR environment variable)",
    )
    args = parser.parse_args()
    success = merge_pyproject(args.target_dir, args.tooling_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
