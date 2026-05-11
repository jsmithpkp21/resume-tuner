"""Compatibility wrapper for ``resume_builder.cover_letter_template`` — see issue #41.

Prefer importing from ``resume_builder.cover_letter_template`` directly. This wrapper keeps
``from scripts.cover_letter_template import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.cover_letter_template import *  # noqa: F401, F403
