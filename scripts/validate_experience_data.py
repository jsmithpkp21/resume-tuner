"""Compatibility wrapper for ``resume_builder.validate_experience_data`` — see issue #41.

Prefer importing from ``resume_builder.validate_experience_data`` directly. This wrapper keeps
``from scripts.validate_experience_data import X`` working and preserves the
``python scripts/validate_experience_data.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.validate_experience_data import *  # noqa: F401, F403
from resume_builder.validate_experience_data import (
    main,  # explicit re-export for CLI dispatch
)

if __name__ == "__main__":
    raise SystemExit(main())
