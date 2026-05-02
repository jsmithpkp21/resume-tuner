#!/usr/bin/env python3
"""Validate and optionally fix dev-tool version pins against the lock file.

Canonical registry: .github/dev-tool-pin-lock.json
Covered locations:
- scripts/run_commitlint.sh    -> COMMITLINT_VERSION="..."
- requirements-dev.txt         -> ruff==X.Y.Z, mypy==X.Y.Z
- .pre-commit-config.yaml      -> rev: vX.Y.Z (ruff-pre-commit, mirrors-mypy)
- Makefile                     -> MARKDOWNLINT_VERSION ?= X.Y.Z (canonical),
                                  and any residual markdownlint-cli@X.Y.Z literals
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

COMMITLINT_VAR_RE = re.compile(
    r'^(?P<prefix>COMMITLINT_VERSION=")(?P<ver>[^"]+)(?P<suffix>")\s*$'
)
REQ_PIN_RE = re.compile(
    r"^(?P<prefix>(?P<pkg>[A-Za-z0-9_.\-]+)==)(?P<ver>[A-Za-z0-9_.\-]+)\s*$"
)
PRECOMMIT_REPO_RE = re.compile(r"^(?P<indent>\s*)-\s+repo:\s*(?P<url>\S+)\s*$")
PRECOMMIT_REV_RE = re.compile(r"^(?P<prefix>\s*rev:\s*)(?P<ref>\S+)\s*$")
MARKDOWNLINT_NPX_RE = re.compile(
    r"(?P<prefix>markdownlint-cli@)(?P<ver>[A-Za-z0-9_.\-]+)"
)
MARKDOWNLINT_VAR_RE = re.compile(
    r"^(?P<prefix>MARKDOWNLINT_VERSION\s*\??=\s*)(?P<ver>[A-Za-z0-9_.\-]+)\s*$"
)

REQ_PACKAGES = {"ruff": "ruff", "mypy": "mypy"}
PRECOMMIT_REPOS = {
    "https://github.com/astral-sh/ruff-pre-commit": "ruff_pre_commit_rev",
    "https://github.com/pre-commit/mirrors-mypy": "mypy_pre_commit_rev",
}

REQUIRED_LOCK_KEYS = frozenset(
    {
        "commitlint_cli",
        "commitlint_config_conventional",
        "ruff",
        "ruff_pre_commit_rev",
        "mypy",
        "mypy_pre_commit_rev",
        "markdownlint_cli",
    }
)

# Keys that must be referenced from a source file. `commitlint_config_conventional`
# is intentionally excluded: it has no distinct source location, and its parity
# with `commitlint_cli` is enforced as a lock-load invariant.
REQUIRED_SOURCE_KEYS = frozenset(
    {
        "commitlint_cli",
        "ruff",
        "ruff_pre_commit_rev",
        "mypy",
        "mypy_pre_commit_rev",
        "markdownlint_cli",
    }
)


@dataclass(frozen=True)
class Mismatch:
    file: Path
    key: str
    expected: str
    actual: str
    location: str


@dataclass(frozen=True)
class FileError:
    file: Path
    error: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate dev-tool pins against .github/dev-tool-pin-lock.json"
    )
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument(
        "--lock-file",
        default=".github/dev-tool-pin-lock.json",
        help="Lock file path relative to --root",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite mismatched pins using lock values",
    )
    return parser.parse_args()


def _load_lock(lock_file: Path) -> dict[str, str]:
    try:
        data = json.loads(lock_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"ERROR: lock file not found: {lock_file}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"ERROR: lock file is not valid JSON: {lock_file}: {exc}"
        ) from exc
    except OSError as exc:
        raise SystemExit(f"ERROR: failed to read lock file {lock_file}: {exc}") from exc

    if not isinstance(data, dict):
        raise SystemExit(
            f"ERROR: lock file top-level JSON must be an object: {lock_file}"
        )

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise SystemExit(
            f"ERROR: unsupported lock schema_version {schema_version!r} in {lock_file} (expected 1)"
        )

    pins = data.get("pins")
    if not isinstance(pins, dict) or not pins:
        raise SystemExit(f"ERROR: lock file missing non-empty 'pins' map: {lock_file}")

    pin_map: dict[str, str] = {}
    for key, value in pins.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise SystemExit(
                f"ERROR: lock pin entries must be string->string: {key!r}={value!r} in {lock_file}"
            )
        pin_map[key] = value

    missing = REQUIRED_LOCK_KEYS - pin_map.keys()
    if missing:
        raise SystemExit(
            f"ERROR: lock file missing required pin key(s): {sorted(missing)} in {lock_file}"
        )

    cli_ver = pin_map["commitlint_cli"]
    cfg_ver = pin_map["commitlint_config_conventional"]
    if cli_ver != cfg_ver:
        raise SystemExit(
            "ERROR: commitlint_cli and commitlint_config_conventional must be the same version "
            f"in {lock_file}: {cli_ver!r} vs {cfg_ver!r}"
        )

    ruff_ver = pin_map["ruff"]
    ruff_rev = pin_map["ruff_pre_commit_rev"]
    if ruff_rev != f"v{ruff_ver}":
        raise SystemExit(
            "ERROR: ruff_pre_commit_rev must be 'v<ruff>': "
            f"ruff={ruff_ver!r}, ruff_pre_commit_rev={ruff_rev!r}"
        )

    mypy_ver = pin_map["mypy"]
    mypy_rev = pin_map["mypy_pre_commit_rev"]
    if mypy_rev != f"v{mypy_ver}":
        raise SystemExit(
            "ERROR: mypy_pre_commit_rev must be 'v<mypy>': "
            f"mypy={mypy_ver!r}, mypy_pre_commit_rev={mypy_rev!r}"
        )

    return pin_map


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _read_lines(path: Path, file_errors: list[FileError]) -> list[str] | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read().splitlines(keepends=True)
    except OSError as exc:
        file_errors.append(FileError(file=path, error=str(exc)))
        return None


def _write_lines(path: Path, lines: list[str], file_errors: list[FileError]) -> bool:
    try:
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("".join(lines))
    except OSError as exc:
        file_errors.append(FileError(file=path, error=str(exc)))
        return False
    return True


def _check_run_commitlint(
    path: Path,
    lock: dict[str, str],
    fix: bool,
    mismatches: list[Mismatch],
    file_errors: list[FileError],
    seen: set[str],
) -> bool:
    lines = _read_lines(path, file_errors)
    if lines is None:
        return False
    expected = lock["commitlint_cli"]
    changed = False
    new_lines: list[str] = []
    for raw in lines:
        content, ending = _split_line_ending(raw)
        match = COMMITLINT_VAR_RE.match(content)
        if not match:
            new_lines.append(raw)
            continue
        seen.add("commitlint_cli")
        actual = match.group("ver")
        if actual != expected:
            mismatches.append(
                Mismatch(
                    file=path,
                    key="commitlint_cli",
                    expected=expected,
                    actual=actual,
                    location="COMMITLINT_VERSION",
                )
            )
            if fix:
                new_lines.append(
                    f"{match.group('prefix')}{expected}{match.group('suffix')}{ending}"
                )
                changed = True
                continue
        new_lines.append(raw)
    if fix and changed:
        return _write_lines(path, new_lines, file_errors)
    return False


def _check_requirements_dev(
    path: Path,
    lock: dict[str, str],
    fix: bool,
    mismatches: list[Mismatch],
    file_errors: list[FileError],
    seen: set[str],
) -> bool:
    lines = _read_lines(path, file_errors)
    if lines is None:
        return False
    changed = False
    new_lines: list[str] = []
    for raw in lines:
        content, ending = _split_line_ending(raw)
        match = REQ_PIN_RE.match(content)
        if not match:
            new_lines.append(raw)
            continue
        pkg = match.group("pkg")
        key = REQ_PACKAGES.get(pkg)
        if key is None:
            new_lines.append(raw)
            continue
        seen.add(key)
        actual = match.group("ver")
        expected = lock[key]
        if actual != expected:
            mismatches.append(
                Mismatch(
                    file=path,
                    key=key,
                    expected=expected,
                    actual=actual,
                    location=f"{pkg}==",
                )
            )
            if fix:
                new_lines.append(f"{match.group('prefix')}{expected}{ending}")
                changed = True
                continue
        new_lines.append(raw)
    if fix and changed:
        return _write_lines(path, new_lines, file_errors)
    return False


def _check_pre_commit_config(
    path: Path,
    lock: dict[str, str],
    fix: bool,
    mismatches: list[Mismatch],
    file_errors: list[FileError],
    seen: set[str],
) -> bool:
    lines = _read_lines(path, file_errors)
    if lines is None:
        return False
    changed = False
    new_lines: list[str] = []
    pending_key: str | None = None
    pending_indent: int | None = None
    for raw in lines:
        content, ending = _split_line_ending(raw)
        repo_match = PRECOMMIT_REPO_RE.match(content)
        if repo_match:
            url = repo_match.group("url")
            pending_key = PRECOMMIT_REPOS.get(url)
            pending_indent = len(repo_match.group("indent"))
            new_lines.append(raw)
            continue
        if pending_key is not None:
            rev_match = PRECOMMIT_REV_RE.match(content)
            if rev_match:
                seen.add(pending_key)
                actual = rev_match.group("ref")
                expected = lock[pending_key]
                if actual != expected:
                    mismatches.append(
                        Mismatch(
                            file=path,
                            key=pending_key,
                            expected=expected,
                            actual=actual,
                            location=f"rev for {pending_key}",
                        )
                    )
                    if fix:
                        new_lines.append(
                            f"{rev_match.group('prefix')}{expected}{ending}"
                        )
                        changed = True
                        pending_key = None
                        pending_indent = None
                        continue
                new_lines.append(raw)
                pending_key = None
                pending_indent = None
                continue
            stripped = content.lstrip()
            if stripped and not stripped.startswith("#"):
                indent = len(content) - len(stripped)
                if pending_indent is not None and indent <= pending_indent:
                    pending_key = None
                    pending_indent = None
        new_lines.append(raw)
    if fix and changed:
        return _write_lines(path, new_lines, file_errors)
    return False


def _check_makefile(
    path: Path,
    lock: dict[str, str],
    fix: bool,
    mismatches: list[Mismatch],
    file_errors: list[FileError],
    seen: set[str],
) -> bool:
    lines = _read_lines(path, file_errors)
    if lines is None:
        return False
    expected = lock["markdownlint_cli"]
    changed = False
    new_lines: list[str] = []
    for raw in lines:
        content, ending = _split_line_ending(raw)
        var_match = MARKDOWNLINT_VAR_RE.match(content)
        if var_match:
            seen.add("markdownlint_cli")
            actual = var_match.group("ver")
            if actual != expected:
                mismatches.append(
                    Mismatch(
                        file=path,
                        key="markdownlint_cli",
                        expected=expected,
                        actual=actual,
                        location="MARKDOWNLINT_VERSION",
                    )
                )
                if fix:
                    new_lines.append(f"{var_match.group('prefix')}{expected}{ending}")
                    changed = True
                    continue
            new_lines.append(raw)
            continue
        line_changed = False
        rebuilt = ""
        last = 0
        for match in MARKDOWNLINT_NPX_RE.finditer(content):
            seen.add("markdownlint_cli")
            actual = match.group("ver")
            rebuilt += content[last : match.start()]
            if actual != expected:
                mismatches.append(
                    Mismatch(
                        file=path,
                        key="markdownlint_cli",
                        expected=expected,
                        actual=actual,
                        location="markdownlint-cli@",
                    )
                )
                if fix:
                    rebuilt += f"{match.group('prefix')}{expected}"
                    line_changed = True
                else:
                    rebuilt += match.group(0)
            else:
                rebuilt += match.group(0)
            last = match.end()
        rebuilt += content[last:]
        if line_changed:
            new_lines.append(rebuilt + ending)
            changed = True
        else:
            new_lines.append(raw)
    if fix and changed:
        return _write_lines(path, new_lines, file_errors)
    return False


def _validate_and_maybe_fix(
    root: Path, lock: dict[str, str], fix: bool
) -> tuple[list[Mismatch], list[FileError], set[str], int]:
    mismatches: list[Mismatch] = []
    file_errors: list[FileError] = []
    seen: set[str] = set()
    files_changed = 0

    targets = (
        (root / "scripts" / "run_commitlint.sh", _check_run_commitlint),
        (root / "requirements-dev.txt", _check_requirements_dev),
        (root / ".pre-commit-config.yaml", _check_pre_commit_config),
        (root / "Makefile", _check_makefile),
    )
    for path, checker in targets:
        if not path.exists():
            file_errors.append(FileError(file=path, error="file not found"))
            continue
        if checker(path, lock, fix, mismatches, file_errors, seen):
            files_changed += 1
    return mismatches, file_errors, seen, files_changed


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    lock_file = root / args.lock_file
    lock = _load_lock(lock_file)
    mismatches, file_errors, seen, files_changed = _validate_and_maybe_fix(
        root, lock, args.fix
    )

    for io_error in file_errors:
        print(
            f"ERROR: failed to process file: {io_error.file.relative_to(root)}: {io_error.error}",
            file=sys.stderr,
        )

    if args.fix and files_changed:
        print(f"FIXED: updated dev-tool pins in {files_changed} file(s)")

    unresolved = [] if args.fix else mismatches
    for mismatch in unresolved:
        print(
            "ERROR: dev-tool pin drift: "
            f"{mismatch.file.relative_to(root)} -> {mismatch.location}: "
            f"got {mismatch.actual!r}, expected {mismatch.expected!r} (key {mismatch.key!r})",
            file=sys.stderr,
        )

    missing_from_sources = sorted(REQUIRED_SOURCE_KEYS - seen)
    for key in missing_from_sources:
        print(
            f"ERROR: lock pin not referenced by any source file: {key}",
            file=sys.stderr,
        )

    has_errors = bool(unresolved or missing_from_sources or file_errors)
    if has_errors:
        if args.fix:
            print(
                "Remediation: re-run check after fix to confirm no unresolved coverage errors.",
                file=sys.stderr,
            )
        else:
            print(
                "Remediation: run `make dev-tool-pin-fix` then `make dev-tool-pin-check`.",
                file=sys.stderr,
            )
        return 1

    print(f"OK: dev-tool pins match lock ({len(seen)} key(s) referenced)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
