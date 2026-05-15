"""Shared helpers for `tests/scripts/`.

Currently exposes `isolated_git_env()` for fixtures that create temp git
repos via subprocess. See `isolated_git_env` docstring for the bug class
this prevents (bug #433).
"""

from __future__ import annotations

import os

# Environment variables that override git's default file / directory
# locations (repo, work tree, index, objects, common dir, and the three
# config-file paths). If a test process inherits any of these (e.g.
# pre-commit's pre-push hook sets `GIT_DIR` to the parent repo's `.git/`),
# then a fixture's `subprocess.run(["git", ...], cwd=temp_repo)` can
# silently operate against the wrong files instead of `cwd`. Bug #433
# documents an instance where this caused `test_precommit_drift_e2e` to
# write `user.name=Tooling Tests` into the tooling repo's own `.git/config`
# under pre-push pytest paths.
#
# Strip these in the subprocess env passed to git invocations so cwd /
# default-location resolution wins. Non-location GIT_* vars (e.g.
# GIT_AUTHOR_NAME, GIT_TERMINAL_PROMPT) are left alone — they're useful
# and don't redirect git's file targets.
_GIT_LOCATION_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_COMMON_DIR",
        "GIT_CONFIG",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
    }
)


def isolated_git_env() -> dict[str, str]:
    """Return `os.environ` minus GIT_* vars that override git's default
    file / directory locations.

    Pass this as the `env=` kwarg to `subprocess.run` for any `git`
    invocation in a test fixture that creates a temp git repo. Without it,
    a `GIT_DIR` (or `GIT_INDEX_FILE`, `GIT_CONFIG*`, etc.) inherited from
    the test runner's parent process will override the cwd / default-path
    resolution and the call will land against the wrong files.

    See bug #433 for the failure mode this prevents.
    """
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}
