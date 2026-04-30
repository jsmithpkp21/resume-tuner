#!/usr/bin/env python3
"""Selective pytest runner — Phase 3 of perf epic #116 (issue #123).

Maps changed files to relevant test paths so the local push-stage `pytest-check`
hook doesn't re-run the full suite for narrow changes. CI's `make test` still
runs everything as the safety net; this only narrows the local hook.

Falls back to the full suite (the safe default) whenever:
- A changed file is in the "infra" set (Makefile, pyproject.toml, Dockerfile,
  docker-compose.yml, requirements*.txt, .pre-commit-config.yaml,
  .tooling-sync-manifest.toml, tooling.toml, .env, VERSION, any path under
  .github/workflows/, any path under project-template/).
- More than `MAX_SELECTIVE_FILES` files changed.
- A changed file has no mapping entry.

Always-run guards (cheap structural checks that catch convention regressions)
run even when the selection is narrow. Empty diff is a no-op exit 0.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPO_ROOT / "tests"

MAX_SELECTIVE_FILES = 10

# Candidate guard tests — cheap, catch convention/contract regressions when
# present. These are filtered to "files that actually exist in this repo" at
# runtime (see `_resolve_always_run`) because this script is synced to consumer
# repos that don't carry every guard. Tooling has all three; consumers
# typically only have `test_consumer_contract.py`.
_CANDIDATE_GUARDS: tuple[str, ...] = (
    "tests/scripts/test_pytest_markers.py",
    "tests/scripts/test_consumer_contract.py",
    "tests/scripts/test_precommit_quality_gate.py",
)


def _resolve_always_run() -> list[str]:
    """Return the subset of `_CANDIDATE_GUARDS` that exists in this repo."""
    return [g for g in _CANDIDATE_GUARDS if (REPO_ROOT / g).is_file()]


# Backwards-compat alias for tests / external callers that imported the constant.
ALWAYS_RUN: tuple[str, ...] = _CANDIDATE_GUARDS

# Any change to these forces the full suite.
INFRA_FILES: frozenset[str] = frozenset(
    {
        "Makefile",
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        "requirements.txt",
        "requirements-dev.txt",
        ".pre-commit-config.yaml",
        ".tooling-sync-manifest.toml",
        "tooling.toml",
        ".env",
        "VERSION",
    }
)

INFRA_PREFIXES: tuple[str, ...] = (
    ".github/workflows/",
    "project-template/",
)

# Explicit non-derivable mappings. The default rule (`scripts/<x>.py` ->
# `tests/scripts/test_<x>.py`) covers the common case; this dict captures
# special cases where the file name doesn't carry the test name.
EXPLICIT_MAPPINGS: dict[str, tuple[str, ...]] = {
    "commitlint.config.mjs": ("tests/scripts/test_commitlint_local_parity.py",),
    "scripts/run_commitlint.sh": ("tests/scripts/test_commitlint_local_parity.py",),
    "scripts/validate_commit_subject.sh": (
        "tests/scripts/test_validate_commit_subject.py",
    ),
}


class GitDeriveError(RuntimeError):
    """Raised when we cannot derive the changed-files set from git.

    Distinguished from a genuinely empty diff so the caller can fall back to
    the full suite (the safe default for a push-stage hook) rather than
    silently skipping pytest.
    """


def _git_run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _has_rev(rev: str) -> bool:
    """True if the given rev resolves in this repo."""
    return _git_run(["rev-parse", "--verify", "--quiet", rev]).returncode == 0


def _default_remote_branch() -> str | None:
    """Return the repo's default remote branch ref (e.g. `origin/main`).

    Tries the symbolic ref `refs/remotes/origin/HEAD` first (set by
    `git clone` and by `git remote set-head origin --auto`). Falls back to
    probing the conventional names `origin/main` and `origin/master` so a
    consumer that has commit history but no symbolic-ref still gets a
    useful base. Returns None when none resolves — caller raises.
    """
    head = _git_run(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"])
    if head.returncode == 0 and head.stdout.strip():
        # Output looks like `refs/remotes/origin/main`; strip the leading dirs.
        ref = head.stdout.strip()
        if ref.startswith("refs/remotes/"):
            return ref[len("refs/remotes/") :]
        return ref
    for candidate in ("origin/main", "origin/master"):
        if _has_rev(candidate):
            return candidate
    return None


def _changed_files_from_git(stage: str) -> list[str]:
    """Ask git for files changed in the relevant range.

    Raises GitDeriveError if the range can't be derived (no upstream and no
    resolvable default remote branch, or git itself fails). Callers should
    treat that as a signal to run the full suite — never as "diff is empty,
    skip pytest".
    """
    if stage == "commit":
        result = _git_run(["diff", "--name-only", "--cached"])
        if result.returncode != 0:
            raise GitDeriveError(
                f"git diff --name-only --cached failed: {result.stderr.strip()}"
            )
        return [line for line in result.stdout.splitlines() if line.strip()]

    # push: prefer the explicit upstream..HEAD range so unstaged working-tree
    # changes don't sneak in.
    upstream = _git_run(["rev-parse", "--abbrev-ref", "@{upstream}"])
    if upstream.returncode == 0 and upstream.stdout.strip():
        ref_range = "@{upstream}..HEAD"
    else:
        # No upstream tracking — common on the first push of a new branch.
        # `HEAD~1..HEAD` (the prior fallback) is too narrow: it covers only the
        # tip commit and misses earlier commits unique to the branch. Resolve
        # the merge-base against the default remote branch instead, so every
        # commit on this branch is included.
        default = _default_remote_branch()
        if default is None:
            raise GitDeriveError(
                "no upstream tracking branch and no resolvable default remote "
                "branch (origin/HEAD, origin/main, origin/master) — cannot "
                "derive diff range"
            )
        base = _git_run(["merge-base", default, "HEAD"])
        if base.returncode != 0 or not base.stdout.strip():
            raise GitDeriveError(
                f"could not find merge-base of {default} and HEAD: "
                f"{base.stderr.strip()}"
            )
        ref_range = f"{base.stdout.strip()}..HEAD"

    result = _git_run(["diff", "--name-only", ref_range])
    if result.returncode != 0:
        raise GitDeriveError(
            f"git diff --name-only {ref_range} failed: {result.stderr.strip()}"
        )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _is_infra(path: str) -> bool:
    if path in INFRA_FILES:
        return True
    return any(path.startswith(prefix) for prefix in INFRA_PREFIXES)


def _derive_test_path(changed: str) -> str | None:
    """Default rule: scripts/<x>.{py,sh} -> tests/scripts/test_<x>.py.

    All existence checks are anchored at REPO_ROOT so the result doesn't
    depend on the caller's CWD (the hook runs from the repo root, but
    `make` targets and tests may invoke the script from elsewhere).
    """
    p = Path(changed)
    if p.parts and p.parts[0] == "scripts" and p.suffix in (".py", ".sh"):
        candidate = TESTS_ROOT / "scripts" / f"test_{p.stem}.py"
        if candidate.is_file():
            return str(candidate.relative_to(REPO_ROOT))
    if (
        p.parts
        and p.parts[0] == "tests"
        and p.suffix == ".py"
        and (REPO_ROOT / p).is_file()
    ):
        # Test file changed directly — run it.
        return changed
    return None


def select(changed: list[str]) -> tuple[bool, list[str], str]:
    """Return (run_full, paths, reason).

    `run_full=True` means run the whole suite. `paths` is meaningful only when
    `run_full=False`. `reason` is for the developer-facing log line.
    """
    if not changed:
        return False, [], "no-changes"

    if len(changed) > MAX_SELECTIVE_FILES:
        return True, [], f"file-count {len(changed)} > {MAX_SELECTIVE_FILES}"

    for path in changed:
        if _is_infra(path):
            return True, [], f"infra-file {path}"

    selected: set[str] = set(_resolve_always_run())
    for path in changed:
        explicit = EXPLICIT_MAPPINGS.get(path)
        if explicit:
            selected.update(explicit)
            continue
        derived = _derive_test_path(path)
        if derived:
            selected.add(derived)
            continue
        return True, [], f"unmapped {path}"

    return False, sorted(selected), "selected"


def _run_pytest(paths: list[str]) -> int:
    # Invoke pytest via the same interpreter running this script so we don't
    # depend on a `pytest` console-script being on PATH (which the
    # pre-commit wrapper only checks for `python3`, not `pytest`).
    cmd = [sys.executable, "-m", "pytest", "-q", "--durations=10"]
    cmd.extend(paths)
    print(f"[selective] running: {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=REPO_ROOT)


def _run_full() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", "--durations=10"]
    print(f"[selective] running: {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=REPO_ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=("commit", "push"),
        default="push",
        help="Pre-commit stage; affects how changed files are derived from git",
    )
    parser.add_argument(
        "--changed-files",
        nargs="*",
        default=None,
        help="Explicit list of changed file paths (skips git invocation; for tests)",
    )
    parser.add_argument(
        "--from-stdin",
        action="store_true",
        help="Read newline-delimited changed file paths from stdin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the selection and exit 0 without invoking pytest",
    )
    args = parser.parse_args(argv)

    git_derive_failed = False
    if args.from_stdin:
        changed = [line.strip() for line in sys.stdin if line.strip()]
    elif args.changed_files is not None:
        changed = list(args.changed_files)
    else:
        try:
            changed = _changed_files_from_git(args.stage)
        except GitDeriveError as exc:
            print(
                f"[selective] git-derive-failed: {exc}; falling back to full suite",
                flush=True,
            )
            git_derive_failed = True
            changed = []

    if git_derive_failed:
        run_full = True
        paths: list[str] = []
        reason = "git-derive-failed"
    else:
        run_full, paths, reason = select(changed)

    # Empty diff is a legitimate "nothing to do" only when the source was
    # explicit (--changed-files / --from-stdin) and the user passed nothing.
    # When git-derived, an empty diff genuinely means no commits to test.
    if not changed and not git_derive_failed:
        print("[selective] no changed files; skipping pytest")
        return 0

    print(f"[selective] decision: {reason}", flush=True)

    if args.dry_run:
        if run_full:
            print("[selective] (dry-run) full suite")
        else:
            print("[selective] (dry-run) " + " ".join(paths))
        return 0

    # Allow tests to short-circuit pytest invocation by setting this env var.
    if os.environ.get("RUN_PYTEST_SELECTIVE_NO_EXEC") == "1":
        return 0

    if run_full:
        return _run_full()
    return _run_pytest(paths)


if __name__ == "__main__":
    raise SystemExit(main())
