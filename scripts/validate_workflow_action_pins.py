#!/usr/bin/env python3
"""Validate and optionally fix workflow action refs against the action lock file."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

USES_LINE_RE = re.compile(
    r"^(?P<prefix>\s*-?\s*uses:\s*)(?P<uses>[^\s#]+)(?P<suffix>\s*(#.*)?)$"
)


@dataclass(frozen=True)
class Mismatch:
    workflow: Path
    action: str
    expected_ref: str
    actual_ref: str


@dataclass(frozen=True)
class UnknownAction:
    workflow: Path
    action: str
    actual_ref: str


@dataclass(frozen=True)
class FileError:
    workflow: Path
    error: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate workflow uses refs against .github/workflow-action-lock.json"
    )
    parser.add_argument("--root", default=".", help="Repository root path")
    parser.add_argument(
        "--lock-file",
        default=".github/workflow-action-lock.json",
        help="Lock file path relative to --root",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Rewrite mismatched workflow refs using lock values",
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
            "ERROR: unsupported lock schema_version "
            f"{schema_version!r} in {lock_file} (expected 1)"
        )

    actions = data.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise SystemExit(
            f"ERROR: lock file missing non-empty 'actions' map: {lock_file}"
        )
    action_refs: dict[str, str] = {}
    for action, ref in actions.items():
        if not isinstance(action, str):
            raise SystemExit(
                "ERROR: lock action key must be a string "
                f"in {lock_file}: key={action!r}"
            )
        if not isinstance(ref, str):
            raise SystemExit(
                "ERROR: lock action ref must be a string "
                f"in {lock_file}: action={action!r}, ref={ref!r}"
            )
        if "@" in action:
            raise SystemExit(f"ERROR: lock key must be action name only: {action}")
        action_refs[action] = ref
    return action_refs


def _iter_workflows(root: Path) -> list[Path]:
    workflows_dir = root / ".github" / "workflows"
    return sorted(
        list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml"))
    )


def _split_uses(value: str) -> tuple[str, str] | None:
    if value.startswith("./") or "@" not in value:
        return None
    action, ref = value.split("@", 1)
    return action, ref


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def _validate_and_maybe_fix(
    workflows: list[Path], lock_refs: dict[str, str], fix: bool
) -> tuple[list[Mismatch], list[UnknownAction], list[FileError], set[str], int]:
    mismatches: list[Mismatch] = []
    unknown_actions: list[UnknownAction] = []
    file_errors: list[FileError] = []
    seen_actions: set[str] = set()
    files_changed = 0
    for workflow in workflows:
        try:
            with workflow.open("r", encoding="utf-8", newline="") as handle:
                original_lines = handle.read().splitlines(keepends=True)
        except OSError as exc:
            file_errors.append(FileError(workflow=workflow, error=str(exc)))
            continue
        changed = False
        new_lines: list[str] = []
        for line in original_lines:
            line_content, line_ending = _split_line_ending(line)
            match = USES_LINE_RE.match(line_content)
            if not match:
                new_lines.append(line)
                continue
            uses_value = match.group("uses")
            split = _split_uses(uses_value)
            if split is None:
                new_lines.append(line)
                continue
            action, actual_ref = split
            seen_actions.add(action)
            expected_ref = lock_refs.get(action)
            if expected_ref is None:
                unknown_actions.append(
                    UnknownAction(
                        workflow=workflow, action=action, actual_ref=actual_ref
                    )
                )
                new_lines.append(line)
                continue
            if actual_ref != expected_ref:
                mismatches.append(
                    Mismatch(
                        workflow=workflow,
                        action=action,
                        expected_ref=expected_ref,
                        actual_ref=actual_ref,
                    )
                )
                if fix:
                    rewritten = (
                        f"{match.group('prefix')}{action}@{expected_ref}{match.group('suffix')}"
                        f"{line_ending}"
                    )
                    new_lines.append(rewritten)
                    changed = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        if fix and changed:
            try:
                with workflow.open("w", encoding="utf-8", newline="") as handle:
                    handle.write("".join(new_lines))
            except OSError as exc:
                file_errors.append(FileError(workflow=workflow, error=str(exc)))
                continue
            files_changed += 1
    return mismatches, unknown_actions, file_errors, seen_actions, files_changed


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    lock_file = root / args.lock_file
    lock_refs = _load_lock(lock_file)
    workflows = _iter_workflows(root)
    if not workflows:
        print(
            f"ERROR: no workflow files found under {root / '.github' / 'workflows'}",
            file=sys.stderr,
        )
        return 1
    mismatches, unknown_actions, file_errors, seen_actions, files_changed = (
        _validate_and_maybe_fix(
            workflows=workflows,
            lock_refs=lock_refs,
            fix=args.fix,
        )
    )
    for issue in unknown_actions:
        print(
            "ERROR: unknown workflow action not in lock: "
            f"{issue.workflow.relative_to(root)} -> {issue.action}@{issue.actual_ref}",
            file=sys.stderr,
        )
    for io_error in file_errors:
        print(
            "ERROR: failed to process workflow file: "
            f"{io_error.workflow.relative_to(root)}: {io_error.error}",
            file=sys.stderr,
        )

    if args.fix and files_changed:
        print(f"FIXED: updated workflow refs in {files_changed} file(s)")
    unresolved_mismatches: list[Mismatch] = []
    if not args.fix:
        unresolved_mismatches = mismatches
    for mismatch in unresolved_mismatches:
        print(
            "ERROR: workflow action drift: "
            f"{mismatch.workflow.relative_to(root)} -> "
            f"{mismatch.action}@{mismatch.actual_ref} "
            f"(expected {mismatch.expected_ref})",
            file=sys.stderr,
        )
    missing_from_workflows = sorted(set(lock_refs) - seen_actions)
    for action in missing_from_workflows:
        print(
            f"ERROR: action lock entry is not used by any workflow: {action}",
            file=sys.stderr,
        )
    has_errors = bool(
        unknown_actions
        or unresolved_mismatches
        or missing_from_workflows
        or file_errors
    )
    if has_errors:
        if args.fix:
            print(
                "Remediation: re-run check after fix to confirm no unresolved lock coverage errors.",
                file=sys.stderr,
            )
        else:
            print(
                "Remediation: run `make action-pin-fix` then `make action-pin-check`.",
                file=sys.stderr,
            )
        return 1
    print(
        "OK: workflow action refs match lock "
        f"({len(seen_actions)} action(s), {len(workflows)} workflow file(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
