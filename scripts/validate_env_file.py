#!/usr/bin/env python3
"""Validate .env stays in sync with tooling.toml build inputs.

Docker Compose auto-loads .env to populate PYTHON_VERSION and PIP_VERSION build
args. tooling.toml is the source of truth for both. This script enforces that
.env values match tooling.toml so Compose builds never silently use stale pins.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

REQUIRED_KEYS = ("PYTHON_VERSION", "PIP_VERSION")


def _read_tooling_versions(tooling_path: Path) -> dict[str, str]:
    data = tomllib.loads(tooling_path.read_text(encoding="utf-8"))

    python_section = data.get("python")
    if not isinstance(python_section, dict):
        raise ValueError(f"{tooling_path.name} missing [python] section")
    python_version = python_section.get("version")
    if not isinstance(python_version, str) or not python_version.strip():
        raise ValueError(f"{tooling_path.name} missing [python].version")

    tooling_section = data.get("tooling")
    if not isinstance(tooling_section, dict):
        raise ValueError(f"{tooling_path.name} missing [tooling] section")
    pip_version = tooling_section.get("pip")
    if not isinstance(pip_version, str) or not pip_version.strip():
        raise ValueError(f"{tooling_path.name} missing [tooling].pip")

    return {
        "PYTHON_VERSION": python_version.strip(),
        "PIP_VERSION": pip_version.strip(),
    }


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for lineno, raw in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{env_path.name}:{lineno} malformed (missing '='): {raw}")
        key, _, value = line.partition("=")
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError(f"{env_path.name}:{lineno} invalid key: {key!r}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def _write_env_file(env_path: Path, expected: dict[str, str]) -> None:
    existing = (
        env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    )
    seen: set[str] = set()
    new_lines: list[str] = []
    for raw in existing:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(raw)
            continue
        key = stripped.partition("=")[0].strip()
        if key in expected:
            new_lines.append(f"{key}={expected[key]}")
            seen.add(key)
        else:
            new_lines.append(raw)
    for key in REQUIRED_KEYS:
        if key not in seen:
            new_lines.append(f"{key}={expected[key]}")
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def run(root: Path, fix: bool = False) -> int:
    tooling_path = root / "tooling.toml"
    env_path = root / ".env"

    # Skip cleanly when either input is absent. Consumers that don't use Docker
    # Compose may not have .env, and consumers that don't track tooling.toml
    # have nothing to drift against. Either case is a no-op, not an error, so
    # `make check` and the pre-commit hook stay green for those repos.
    if not tooling_path.exists():
        print(f"SKIP: tooling.toml not found at {tooling_path}; nothing to check.")
        return 0
    if not env_path.exists():
        print(f"SKIP: .env not found at {env_path}; nothing to check.")
        return 0

    try:
        expected = _read_tooling_versions(tooling_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        actual = _read_env_file(env_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    mismatches: list[tuple[str, str, str]] = []
    for key in REQUIRED_KEYS:
        if key not in actual:
            mismatches.append((key, "<missing>", expected[key]))
        elif actual[key] != expected[key]:
            mismatches.append((key, actual[key], expected[key]))

    if not mismatches:
        print(
            f"OK: .env matches tooling.toml "
            f"(PYTHON_VERSION={expected['PYTHON_VERSION']}, "
            f"PIP_VERSION={expected['PIP_VERSION']})"
        )
        return 0

    if not fix:
        print("ERROR: .env drift detected vs tooling.toml:", file=sys.stderr)
        for key, found, expected_val in mismatches:
            print(
                f"  - {key}: .env={found!r} tooling.toml={expected_val!r}",
                file=sys.stderr,
            )
        print(
            "Fix: run `python3 scripts/validate_env_file.py --root . --fix` "
            "or update .env to match tooling.toml.",
            file=sys.stderr,
        )
        return 1

    _write_env_file(env_path, expected)
    print(
        f"OK: .env synchronized to tooling.toml "
        f"(PYTHON_VERSION={expected['PYTHON_VERSION']}, "
        f"PIP_VERSION={expected['PIP_VERSION']})"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate .env matches tooling.toml build-input pins"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite .env to match tooling.toml when drift is detected",
    )
    args = parser.parse_args()
    raise SystemExit(run(args.root.resolve(), fix=args.fix))


if __name__ == "__main__":
    main()
