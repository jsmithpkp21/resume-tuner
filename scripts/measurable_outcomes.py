"""Compatibility wrapper for ``resume_builder.measurable_outcomes`` — see issue #41.

Prefer importing from ``resume_builder.measurable_outcomes`` directly. This wrapper keeps
``from scripts.measurable_outcomes import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.measurable_outcomes import *  # noqa: F401, F403
