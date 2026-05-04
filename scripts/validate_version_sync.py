#!/usr/bin/env python3
"""Validate and optionally auto-fix project version consistency across metadata files."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path


def _read_version_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    first = lines[0] if lines else ""
    value = first.split("#", 1)[0].strip()
    if not value:
        raise ValueError(f"{path.name} is empty")
    # VERSION must be a single semver line plus an optional release-please
    # annotation; any extra non-blank line is corruption (e.g. a stray append)
    # that would otherwise be silently ignored and bypass version-sync checks.
    for extra in lines[1:]:
        if extra.strip():
            raise ValueError(
                f"{path.name} must contain a single version line; "
                f"extra content found: {extra!r}"
            )
    return value


def _version_file_needs_annotation(path: Path) -> bool:
    # The release-please `generic` extra-files updater bumps a line only when
    # it carries the `x-release-please-version` marker, so a missing marker is
    # itself a form of drift even when all four version literals already agree
    # (issue #296). `_read_version_file` strips comments before comparison, so
    # the equality check in `run()` cannot detect this on its own.
    if not path.exists():
        return False
    first = next(iter(path.read_text(encoding="utf-8").splitlines()), "")
    return "x-release-please-version" not in first


def _write_version_file(path: Path, version: str) -> None:
    # Always emit the `x-release-please-version` annotation. Release-please's
    # `generic` extra-files updater only rewrites lines carrying that marker,
    # so an unannotated VERSION silently drifts on every release (issues #272,
    # #296). Writing the annotation unconditionally upgrades consumer repos
    # the first time `--fix` runs (locally, in the pre-commit hook, or via the
    # post-release-sync workflow), and leaves already-annotated files
    # unchanged. Other VERSION readers strip `#` comments, so the annotation
    # is inert for them.
    path.write_text(f"{version} # x-release-please-version\n", encoding="utf-8")


def _read_project_version(path: Path) -> str:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"{path.name} missing [project] section")

    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{path.name} missing [project].version")

    return version.strip()


def _set_project_version(path: Path, version: str) -> None:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    in_project = False
    saw_project = False
    section_end_index: int | None = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("[") and stripped.endswith("]"):
            if in_project:
                section_end_index = i
                break
            in_project = stripped == "[project]"
            if in_project:
                saw_project = True
            continue

        if in_project and re.match(r"^\s*version\s*=", line):
            indent = line[: len(line) - len(line.lstrip())]
            newline = "\n" if line.endswith("\n") else ""
            lines[i] = f'{indent}version = "{version}"{newline}'
            path.write_text("".join(lines), encoding="utf-8")
            return

    if not saw_project:
        raise ValueError(f"{path.name} missing [project] section")

    insert_at = len(lines) if section_end_index is None else section_end_index
    lines.insert(insert_at, f'version = "{version}"\n')
    path.write_text("".join(lines), encoding="utf-8")


def _read_manifest_version(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path.name} is not valid JSON") from exc

    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must contain a JSON object")

    version = data.get(".")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"{path.name} missing '.' version entry")

    return version.strip()


def _set_manifest_version(path: Path, version: str) -> None:
    data: dict[str, object]
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name} is not valid JSON") from exc

        if not isinstance(existing, dict):
            raise ValueError(f"{path.name} must contain a JSON object")

        data = existing
    else:
        data = {}

    data["."] = version
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _apply_fix(
    version_path: Path,
    meta_path: Path,
    pyproject_path: Path,
    manifest_path: Path,
    version: str,
) -> None:
    _write_version_file(version_path, version)
    _set_project_version(meta_path, version)
    _set_project_version(pyproject_path, version)
    _set_manifest_version(manifest_path, version)


def _collect_versions(
    version_path: Path, meta_path: Path, pyproject_path: Path, manifest_path: Path
) -> dict[str, str]:
    return {
        "VERSION": _read_version_file(version_path),
        ".pyproject.meta.toml": _read_project_version(meta_path),
        "pyproject.toml": _read_project_version(pyproject_path),
        ".release-please-manifest.json": _read_manifest_version(manifest_path),
    }


def run(root: Path, fix: bool = False, target_version: str | None = None) -> int:
    version_path = root / "VERSION"
    meta_path = root / ".pyproject.meta.toml"
    pyproject_path = root / "pyproject.toml"
    manifest_path = root / ".release-please-manifest.json"

    missing = [
        p
        for p in (version_path, meta_path, pyproject_path, manifest_path)
        if not p.exists()
    ]
    if missing:
        for path in missing:
            print(f"ERROR: Missing required file: {path}", file=sys.stderr)
        return 1

    try:
        versions = _collect_versions(
            version_path, meta_path, pyproject_path, manifest_path
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # Default to release-please manifest as the source-of-truth unless overridden.
    desired_version = (
        target_version if target_version else versions[".release-please-manifest.json"]
    )
    is_synced = len(set(versions.values())) == 1
    needs_annotation = _version_file_needs_annotation(version_path)

    if not fix and (not is_synced or needs_annotation):
        if not is_synced:
            print("ERROR: Version mismatch detected:", file=sys.stderr)
            for name, value in versions.items():
                print(f"  - {name}: {value}", file=sys.stderr)
        else:
            print(
                "ERROR: VERSION is missing the `# x-release-please-version` "
                "annotation; release-please will not bump it on the next release.",
                file=sys.stderr,
            )
        print(
            "Fix: run `python3 scripts/validate_version_sync.py --root . --fix` "
            "or set an explicit version with `--version X.Y.Z --fix`.",
            file=sys.stderr,
        )
        return 1

    if fix and (not is_synced or needs_annotation or target_version is not None):
        try:
            _apply_fix(
                version_path,
                meta_path,
                pyproject_path,
                manifest_path,
                desired_version,
            )
            versions = _collect_versions(
                version_path, meta_path, pyproject_path, manifest_path
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    if len(set(versions.values())) != 1 or versions["VERSION"] != desired_version:
        print("ERROR: Failed to synchronize versions:", file=sys.stderr)
        for name, value in versions.items():
            print(f"  - {name}: {value}", file=sys.stderr)
        return 1

    if fix:
        print(f"OK: Version synchronized ({versions['VERSION']})")
    else:
        print(f"OK: Version is in sync ({versions['VERSION']})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate VERSION/.pyproject.meta.toml/pyproject.toml/"
            ".release-please-manifest.json stay in sync"
        )
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix mismatches by rewriting all version locations",
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Explicit version to apply to all version locations (requires --fix)",
    )
    args = parser.parse_args()

    if args.version is not None and not args.fix:
        print("ERROR: --version requires --fix", file=sys.stderr)
        raise SystemExit(2)

    root = args.root.resolve()
    raise SystemExit(run(root, fix=args.fix, target_version=args.version))


if __name__ == "__main__":
    main()
