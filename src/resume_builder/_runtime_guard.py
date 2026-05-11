"""Shared runtime blocked-input guard (#20).
Single source of truth for the blocklist policy: runtime inputs that resolve
into ``sandbox/`` or ``data/samples/`` are rejected before any file I/O.
Both ``validate_experience_data`` and ``generate_review_packet`` import from
here so the blocked-root definition cannot drift between scripts.
"""

from __future__ import annotations

from pathlib import Path

# File now lives at src/resume_builder/_runtime_guard.py (issue #41 refactor),
# so the repo root is three parents up rather than two.
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_BLOCKED_RUNTIME_ROOTS: frozenset[Path] = frozenset(
    {
        _PROJECT_ROOT / "sandbox",
        _PROJECT_ROOT / "data" / "samples",
    }
)


def assert_not_blocked_runtime_input(path: Path) -> None:
    """Raise ``ValueError`` if *path* resolves into a blocked runtime directory.
    This is a blocklist guard (not a strict allowlist): runtime inputs are
    rejected only when they resolve into one of the blocked roots
    (``sandbox/`` or ``data/samples/``).  Other paths - including arbitrary
    temp-directory paths used in tests - are accepted.
    """
    resolved = path.resolve()
    for blocked in _BLOCKED_RUNTIME_ROOTS:
        if resolved.is_relative_to(blocked.resolve()):
            blocked_display = blocked.relative_to(_PROJECT_ROOT).as_posix()
            raise ValueError(
                f"Path '{path}' resolves into blocked runtime directory "
                f"'{blocked_display}/'. "
                f"Runtime inputs may not resolve into blocked directories such as "
                f"sandbox/ or data/samples/."
            )
