#!/usr/bin/env python3
"""Prepare Playwright layer from base environment.

This script verifies the base environment and writes a Playwright-specific
requirements.txt and LAYER_METADATA.toml under layers/playwright/.

Run from the repo root. It is safe to run repeatedly (idempotent).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path


def read_version() -> str:
    """Read environment version from VERSION file.

    Returns:
        Version string (e.g., "0.1.0").

    Raises:
        FileNotFoundError: If `VERSION` file doesn't exist.
        ValueError: If `VERSION` file is empty.
    """
    version_file: str = "VERSION"

    if not os.path.exists(version_file):
        raise FileNotFoundError(f"VERSION file not found at {version_file}")

    with open(version_file) as f:
        version: str = f.read().strip()

    if not version:
        raise ValueError("VERSION file is empty")

    return version


def read_requirements(path: str = "requirements.txt") -> list[str]:
    """Read a requirements file and return normalized list of lines.

    Comments and blank lines are filtered out.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Requirements file not found: {path}")

    requirements: list[str] = []
    with open(path) as f:
        for raw in f:
            line: str = raw.strip()
            if not line or line.startswith("#"):
                continue
            requirements.append(line)
    return requirements


def get_installed_packages(
    python_executable: str = sys.executable, timeout: int = 30
) -> set[str]:
    """Return a set of installed package names (lowercased) via `pip freeze`.

    Args:
        python_executable: Python interpreter to query.
        timeout: Timeout in seconds for the pip command.

    Returns:
        Set of installed package names (lowercase).

    Raises:
        OSError: If pip command fails or times out.
    """
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [python_executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        raise OSError(f"pip freeze timed out after {timeout}s") from e
    except FileNotFoundError as e:
        raise OSError(f"Python executable not found: {python_executable}") from e
    except Exception as e:
        raise OSError(f"Unexpected error running pip: {e}") from e

    if result.returncode != 0:
        raise OSError(f"pip freeze failed: {result.stderr.strip()}")

    packages: set[str] = set()
    for line in result.stdout.splitlines():
        if "==" in line:
            name: str = line.split("==", 1)[0].lower()
        elif "@" in line:
            name = line.split("@", 1)[0].strip().lower()
        else:
            name = line.split("=", 1)[0].split(">=", 1)[0].strip().lower()
        if name:
            packages.add(name)
    return packages


def verify_requirements_installed(
    requirements: list[str], python_executable: str = sys.executable
) -> tuple[bool, list[str]]:
    """Verify that all requirement package names are installed.

    Returns a tuple of (all_installed, missing_list).
    """
    installed: set[str] = get_installed_packages(python_executable)
    missing: list[str] = []

    for req in requirements:
        name: str = req.split(";", 1)[0].split("[", 1)[0]
        for sep in ("==", ">=", "<=", "~=", ">", "<", "!="):
            if sep in name:
                name = name.split(sep, 1)[0]
        name = name.strip().lower()
        if name and name not in installed:
            missing.append(req)
    return (len(missing) == 0, missing)


def read_pyproject_target() -> str | None:
    """Read `tool.ruff.target-version` from `pyproject.toml` if present.

    Returns:
        Target version string like "py311" or None if not configured.
    """
    pyproject_path: str = "pyproject.toml"
    if not os.path.exists(pyproject_path):
        return None

    with open(pyproject_path, "rb") as f:
        data_raw = tomllib.load(f)

    # Make sure we handle the nested dicts safely for type checking
    tool_obj = data_raw.get("tool") if isinstance(data_raw, dict) else None
    if isinstance(tool_obj, dict):
        tool = tool_obj
    else:
        tool = {}

    ruff_obj = tool.get("ruff") if isinstance(tool, dict) else None
    if isinstance(ruff_obj, dict):
        ruff = ruff_obj
    else:
        ruff = {}
    target = ruff.get("target-version")
    return target


def verify_base_env(python_prefix: str = "3.11") -> dict[str, object]:
    """Verify base environment: Python version, VERSION file, and requirements.

    Returns a dict with verification results.
    """
    results: dict[str, object] = {
        "python_ok": False,
        "python_version": None,
        "env_version": None,
        "requirements_ok": False,
        "missing": [],
    }

    # Python version
    try:
        proc: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as e:
        raise OSError(f"Failed to check Python version: {e}") from e

    output: str = (proc.stdout or proc.stderr or "").strip()
    results["python_version"] = output
    results["python_ok"] = output.startswith(f"Python {python_prefix}")

    # VERSION
    try:
        results["env_version"] = read_version()
    except Exception as e:
        results["env_version_error"] = str(e)

    # Requirements
    try:
        reqs: list[str] = read_requirements()
        ok, missing = verify_requirements_installed(reqs)
        results["requirements_ok"] = ok
        results["missing"] = missing
    except FileNotFoundError as e:
        results["requirements_error"] = str(e)

    return results


class PlaywrightEnvBuilder:
    """Prepare a Playwright environment layer from the base environment."""

    def __init__(self, layer_dir: str = "layers/playwright") -> None:
        """Initialize builder and ensure layer directory exists."""
        self.layer_dir: Path = Path(layer_dir)
        self.layer_dir.mkdir(parents=True, exist_ok=True)

    def prepare_requirements(
        self, base_requirements: list[str], extra_packages: list[str] | None = None
    ) -> str:
        """Prepare combined requirements for the Playwright layer.

        Returns path to the written requirements file.
        """
        extras: list[str] = extra_packages or [
            "playwright==1.35.0",
            "pytest-playwright>=0.4.0",
        ]
        # preserve order and uniqueness
        seen: set[str] = set()
        combined: list[str] = []
        for line in base_requirements + extras:
            key = (
                line.split("==", 1)[0].split("[", 1)[0].split(";", 1)[0].strip().lower()
            )
            if key and key not in seen:
                seen.add(key)
                combined.append(line)

        out_path: Path = self.layer_dir.joinpath("requirements.txt")
        with out_path.open("w", encoding="utf-8") as f:
            for line in combined:
                f.write(f"{line}\n")
        return str(out_path)

    def prepare_layer_metadata(self, metadata: dict[str, str] | None = None) -> str:
        """Write a minimal metadata file for the layer and return its path."""
        meta: dict[str, str] = metadata or {
            "layer": "playwright",
            "source": "generated",
        }
        out_path: Path = self.layer_dir.joinpath("LAYER_METADATA.toml")
        with out_path.open("w", encoding="utf-8") as f:
            for k, v in meta.items():
                f.write(f'{k} = "{v}"\n')
        return str(out_path)


def main() -> int:
    """CLI entrypoint for verification and Playwright layer preparation.

    Returns exit code 0 on success, non-zero on failure.
    """
    print("Verifying base environment...")
    results = verify_base_env("3.11")
    for k, v in results.items():
        print(f"  {k}: {v}")

    if not results.get("python_ok"):
        print("ERROR: Python version mismatch. Aborting layer creation.")
        return 2

    if not results.get("requirements_ok"):
        print(
            "WARNING: Some base requirements are missing; layer will be generated but may be incomplete."
        )

    try:
        base_reqs = read_requirements()
    except FileNotFoundError:
        base_reqs = []

    builder = PlaywrightEnvBuilder()
    req_path = builder.prepare_requirements(base_reqs)
    meta_path = builder.prepare_layer_metadata(
        {"layer": "playwright", "version": read_version()}
    )

    print(f"Prepared Playwright requirements at: {req_path}")
    print(f"Wrote layer metadata at: {meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
