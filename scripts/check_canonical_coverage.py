"""Compatibility wrapper for ``resume_builder.check_canonical_coverage`` — see issue #41.

Prefer importing from ``resume_builder.check_canonical_coverage`` directly. This wrapper keeps
``from scripts.check_canonical_coverage import X`` working and preserves the
``python scripts/check_canonical_coverage.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.check_canonical_coverage import *  # noqa: F401, F403
from resume_builder.check_canonical_coverage import (
    main,  # explicit re-export for CLI dispatch
)

if __name__ == "__main__":
    raise SystemExit(main())
