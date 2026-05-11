"""Compatibility wrapper for ``resume_builder.cover_letter`` — see issue #41.

Prefer importing from ``resume_builder.cover_letter`` directly. This wrapper keeps
``from scripts.cover_letter import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.cover_letter import *  # noqa: F401, F403
