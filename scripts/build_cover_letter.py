"""Compatibility wrapper for ``resume_builder.build_cover_letter`` — see issue #41.

Prefer importing from ``resume_builder.build_cover_letter`` directly. This wrapper keeps
``from scripts.build_cover_letter import X`` working and preserves the
``python scripts/build_cover_letter.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.build_cover_letter import *  # noqa: F401, F403
from resume_builder.build_cover_letter import (
    main,  # explicit re-export for CLI dispatch
)

if __name__ == "__main__":
    raise SystemExit(main())
