"""Compatibility wrapper for ``resume_builder.build_resume`` — see issue #41.

Prefer importing from ``resume_builder.build_resume`` directly. This wrapper keeps
``from scripts.build_resume import X`` working and preserves the
``python scripts/build_resume.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.build_resume import *  # noqa: F401, F403
from resume_builder.build_resume import main  # explicit re-export for CLI dispatch

if __name__ == "__main__":
    raise SystemExit(main())
