"""Compatibility wrapper for ``resume_builder._runtime_guard`` — see issue #41.

Prefer importing from ``resume_builder._runtime_guard`` directly. This wrapper keeps
``from scripts._runtime_guard import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder._runtime_guard import *  # noqa: F401, F403
