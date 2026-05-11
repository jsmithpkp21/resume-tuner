"""Compatibility wrapper for ``resume_builder.cover_letter_export`` — see issue #41.

Prefer importing from ``resume_builder.cover_letter_export`` directly. This wrapper keeps
``from scripts.cover_letter_export import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.cover_letter_export import *  # noqa: F401, F403
