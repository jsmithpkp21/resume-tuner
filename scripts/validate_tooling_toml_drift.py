from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:  # pragma: no cover - exercised via subprocess test
    # Python <3.11 lacks stdlib tomllib. Defer the hard failure to the point
    # of use so skip paths (missing lock/tooling.toml) still complete cleanly.
    tomllib = None  # type: ignore[assignment]

LOCK_FILE_NAME = ".tooling-sync-manifest.lock"
TOOLING_TOML_NAME = "tooling.toml"


def _load_tooling_toml_version(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"SECURITY: {TOOLING_TOML_NAME} must not be a symbolic link.")
    if tomllib is None:
        raise ValueError(
            f"ENV: Python 3.11+ required to parse {TOOLING_TOML_NAME} "
            "(tomllib not available). Run `make setup` to create the pinned "
            "virtualenv, or upgrade your interpreter."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(
            f"MALFORMED: failed to parse {TOOLING_TOML_NAME}: {exc}"
        ) from exc

    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(
            f"MALFORMED: {TOOLING_TOML_NAME} is missing a top-level string `version` field."
        )
    return version


def _load_lock_requested_ref(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"SECURITY: {LOCK_FILE_NAME} must not be a symbolic link.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"MALFORMED: failed to parse {LOCK_FILE_NAME}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"MALFORMED: {LOCK_FILE_NAME} must contain a JSON object.")

    requested_ref = data.get("requested_ref")
    if not isinstance(requested_ref, str) or not requested_ref:
        raise ValueError(
            f"MALFORMED: {LOCK_FILE_NAME} is missing a string `requested_ref` field."
        )
    return requested_ref


def validate_tooling_toml_drift(root: Path) -> int:
    root_resolved = root.resolve()
    tooling_toml_path = root_resolved / TOOLING_TOML_NAME
    lock_path = root_resolved / LOCK_FILE_NAME

    # Symlink checks must run before exists(): Path.exists() follows symlinks,
    # so a *broken* symlink at either path would otherwise be reported as
    # "missing" and silently skipped, bypassing the SECURITY guard. Failing
    # closed on any symlink (broken or not) matches validate_sync_drift.py.
    if lock_path.is_symlink():
        print(
            f"SECURITY: {LOCK_FILE_NAME} must not be a symbolic link.",
            file=sys.stderr,
        )
        return 2

    if tooling_toml_path.is_symlink():
        print(
            f"SECURITY: {TOOLING_TOML_NAME} must not be a symbolic link.",
            file=sys.stderr,
        )
        return 2

    if not lock_path.exists():
        print(
            f"tooling-toml-check: no {LOCK_FILE_NAME} found "
            "(tooling source or pre-first-sync consumer) -- skipping"
        )
        return 0

    # Regular-file guard: a FIFO, device, or directory at the lock path would
    # cause read_text() to block or misbehave, potentially hanging make check.
    # Matches validate_sync_drift.py's MALFORMED contract for the same case.
    if not lock_path.is_file():
        print(
            f"MALFORMED: {LOCK_FILE_NAME} must be a regular file.",
            file=sys.stderr,
        )
        return 2

    if not tooling_toml_path.exists():
        print(
            f"tooling-toml-check: no {TOOLING_TOML_NAME} found "
            "(consumer opts out of local version pin) -- skipping"
        )
        return 0

    if not tooling_toml_path.is_file():
        print(
            f"MALFORMED: {TOOLING_TOML_NAME} must be a regular file.",
            file=sys.stderr,
        )
        return 2

    try:
        toml_version = _load_tooling_toml_version(tooling_toml_path)
        lock_ref = _load_lock_requested_ref(lock_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if toml_version != lock_ref:
        print(
            f"DRIFT: {TOOLING_TOML_NAME}.version={toml_version!r} does not match "
            f"{LOCK_FILE_NAME}.requested_ref={lock_ref!r}.",
            file=sys.stderr,
        )
        print(
            "Remediation: bump tooling.toml as part of your sync PR, "
            "or re-run `make sync-tooling TOOLING_VERSION=<ref>` "
            "to regenerate the lock against the pinned version.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {TOOLING_TOML_NAME}.version ({toml_version}) matches "
        f"{LOCK_FILE_NAME}.requested_ref"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that tooling.toml's pinned version matches "
            ".tooling-sync-manifest.lock's requested_ref."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root containing tooling.toml and .tooling-sync-manifest.lock (default: current directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(validate_tooling_toml_drift(args.root))
