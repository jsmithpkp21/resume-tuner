"""Compatibility wrapper for ``resume_builder.generate_review_packet`` — see issue #41.

Prefer importing from ``resume_builder.generate_review_packet`` directly. This wrapper keeps
``from scripts.generate_review_packet import X`` working and preserves the
``python scripts/generate_review_packet.py`` CLI entry.
"""

from __future__ import annotations

from resume_builder.generate_review_packet import *  # noqa: F401, F403
from resume_builder.generate_review_packet import (
    main,  # explicit re-export for CLI dispatch
)

if __name__ == "__main__":
    raise SystemExit(main())
