"""Compatibility wrapper for ``resume_builder.resume_templates`` — see issue #41.

Prefer importing from ``resume_builder.resume_templates`` directly. This wrapper keeps
``from scripts.resume_templates import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.resume_templates import *  # noqa: F401, F403
