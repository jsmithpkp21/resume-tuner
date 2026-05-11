"""Compatibility wrapper for ``resume_builder.llm_client`` — see issue #41.

Prefer importing from ``resume_builder.llm_client`` directly. This wrapper keeps
``from scripts.llm_client import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.llm_client import *  # noqa: F401, F403
