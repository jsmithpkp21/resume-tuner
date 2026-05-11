"""Compatibility wrapper for ``resume_builder.measure_skills_lines`` — see issue #41.

Prefer importing from ``resume_builder.measure_skills_lines`` directly. This wrapper keeps
``from scripts.measure_skills_lines import X`` working and preserves the
``python scripts/measure_skills_lines.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.measure_skills_lines import *  # noqa: F401, F403
from resume_builder.measure_skills_lines import (
    main,  # explicit re-export for CLI dispatch
)

if __name__ == "__main__":
    raise SystemExit(main())
