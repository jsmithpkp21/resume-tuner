"""Compatibility wrapper for ``resume_builder.select_skills`` — see issue #41.

Prefer importing from ``resume_builder.select_skills`` directly. This wrapper keeps
``from scripts.select_skills import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.select_skills import *  # noqa: F401, F403
