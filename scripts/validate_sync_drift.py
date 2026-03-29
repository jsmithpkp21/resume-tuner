from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

LOCK_FILE_NAME = ".tooling-sync-manifest.lock"
SUPPORTED_SCHEMA_VERSION = 1
SUPPORTED_SOURCE_MODES = {"filesystem", "git"}


def _sha256_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            f"MALFORMED: failed to read managed file '{path}': {exc}"
        ) from exc
    return hashlib.sha256(data).hexdigest()


def _is_safe_repo_relative_path(path: str) -> bool:
    if not path:
        return False

    # Enforce POSIX-style relative paths only.
    if "\\" in path:
        return False
    if path.startswith("/") or path.startswith("//"):
        return False

    # Reject drive-style prefixes in the first segment (for example C: or D:).
    first_segment = path.split("/", 1)[0]
    if ":" in first_segment:
        return False

    # Reject anything this runtime treats as absolute.
    if Path(path).is_absolute():
        return False

    return all(part not in {"", ".", ".."} for part in Path(path).parts)


def _is_lower_hex(value: str, *, length: int) -> bool:
    return len(value) == length and all(ch in "0123456789abcdef" for ch in value)


def _load_lock(lock_path: Path) -> dict[str, object]:
    if lock_path.is_symlink():
        raise ValueError(
            f"SECURITY: {LOCK_FILE_NAME} must not be a symbolic link. Re-run sync-tooling to regenerate managed-file metadata."
        )

    if not lock_path.exists():
        raise ValueError(
            f"MALFORMED: {LOCK_FILE_NAME} is missing. Re-run sync-tooling to initialize managed-file metadata."
        )

    if not lock_path.is_file():
        raise ValueError(
            f"MALFORMED: {LOCK_FILE_NAME} must be a regular file. Re-run sync-tooling to regenerate managed-file metadata."
        )

    try:
        try:
            contents = lock_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"MALFORMED: failed to read {LOCK_FILE_NAME}: {exc}"
            ) from exc
        data = json.loads(contents)
    except json.JSONDecodeError as exc:
        raise ValueError(f"MALFORMED: failed to parse {LOCK_FILE_NAME}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"MALFORMED: {LOCK_FILE_NAME} must contain a JSON object")

    return cast(dict[str, object], data)


def _validate_lock_schema(lock: dict[str, object]) -> dict[str, dict[str, str]]:
    schema_version = lock.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"MALFORMED: unsupported schema_version {schema_version!r}; expected {SUPPORTED_SCHEMA_VERSION}."
        )

    for field in (
        "generated_at_utc",
        "requested_ref",
        "source_mode",
        "resolved_ref",
        "files",
    ):
        if field not in lock:
            raise ValueError(f"MALFORMED: missing required lock field: {field}")

    source_mode = lock.get("source_mode")
    if not isinstance(source_mode, str):
        raise ValueError("MALFORMED: lock field 'source_mode' must be a string")
    if source_mode not in SUPPORTED_SOURCE_MODES:
        raise ValueError(
            "MALFORMED: lock field 'source_mode' must be one of "
            f"{sorted(SUPPORTED_SOURCE_MODES)!r}, not {source_mode!r}"
        )

    resolved_ref = lock.get("resolved_ref")
    if source_mode == "filesystem":
        if resolved_ref is not None:
            raise ValueError(
                "MALFORMED: lock field 'resolved_ref' must be null when source_mode is 'filesystem'"
            )
    else:
        if not isinstance(resolved_ref, str) or not _is_lower_hex(
            resolved_ref, length=40
        ):
            raise ValueError(
                "MALFORMED: lock field 'resolved_ref' must be a 40-character lowercase hex string when source_mode is 'git'"
            )

    tooling_repo = lock.get("tooling_repo")
    if tooling_repo is not None and not isinstance(tooling_repo, str):
        raise ValueError(
            "MALFORMED: lock field 'tooling_repo' must be a string when present"
        )

    files = lock["files"]
    if not isinstance(files, dict) or not files:
        raise ValueError("MALFORMED: lock field 'files' must be a non-empty object")

    validated: dict[str, dict[str, str]] = {}
    for rel_path, metadata in files.items():
        if not isinstance(rel_path, str) or not _is_safe_repo_relative_path(rel_path):
            raise ValueError(f"MALFORMED: invalid managed path in lock: {rel_path!r}")
        if not isinstance(metadata, dict):
            raise ValueError(
                f"MALFORMED: file metadata for {rel_path} must be an object"
            )
        sha256 = metadata.get("sha256")
        if not isinstance(sha256, str) or not _is_lower_hex(sha256, length=64):
            raise ValueError(f"MALFORMED: invalid sha256 for {rel_path}")
        validated[rel_path] = {"sha256": sha256}

    return validated


def _resolve_managed_file(root: Path, rel_path: str) -> tuple[Path | None, str | None]:
    file_path = root / rel_path

    if file_path.is_symlink():
        return None, f"SECURITY: Managed path is a symlink: {rel_path}"

    try:
        resolved_path = file_path.resolve(strict=True)
    except FileNotFoundError:
        return None, None
    except (PermissionError, OSError, RuntimeError) as exc:
        return None, f"SECURITY: Failed to resolve managed path '{rel_path}': {exc}"

    try:
        resolved_path.relative_to(root)
    except ValueError:
        return None, f"SECURITY: Managed path escapes project root: {rel_path}"

    if resolved_path != file_path:
        return None, f"SECURITY: Managed path uses symlink traversal: {rel_path}"

    if not resolved_path.is_file():
        return None, None

    return resolved_path, None


def validate_sync_drift(root: Path) -> int:
    root_resolved = root.resolve()
    lock_path = root_resolved / LOCK_FILE_NAME
    try:
        lock = _load_lock(lock_path)
        files = _validate_lock_schema(lock)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    missing: list[str] = []
    drifted: list[tuple[str, str, str]] = []

    for rel_path in sorted(files):
        expected_sha = files[rel_path]["sha256"]
        resolved_path, security_error = _resolve_managed_file(root_resolved, rel_path)
        if security_error is not None:
            print(security_error, file=sys.stderr)
            return 2
        if resolved_path is None:
            missing.append(rel_path)
            continue

        try:
            actual_sha = _sha256_file(resolved_path)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if actual_sha != expected_sha:
            drifted.append((rel_path, expected_sha, actual_sha))

    for rel_path in missing:
        print(f"MISSING: {rel_path}")
    for rel_path, expected_sha, actual_sha in drifted:
        print(f"DRIFT: {rel_path} (expected {expected_sha}, actual {actual_sha})")

    if missing or drifted:
        print(
            "Remediation: re-run sync-tooling to restore managed files, or update tooling source before regenerating the lock."
        )
        return 1

    print(f"OK: {len(files)} managed file(s) match {LOCK_FILE_NAME}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate synced managed files against .tooling-sync-manifest.lock",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root containing .tooling-sync-manifest.lock (default: current directory)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(validate_sync_drift(args.root.resolve()))
