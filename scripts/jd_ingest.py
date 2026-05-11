"""Compatibility wrapper for ``resume_builder.jd_ingest`` — see issue #41.

Prefer importing from ``resume_builder.jd_ingest`` directly. This wrapper keeps
``from scripts.jd_ingest import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.jd_ingest import *  # noqa: F401, F403
