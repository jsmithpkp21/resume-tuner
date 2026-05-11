"""Compatibility wrapper for ``resume_builder.document_export`` — see issue #41.

Prefer importing from ``resume_builder.document_export`` directly. This wrapper keeps
``from scripts.document_export import X`` working for existing call sites.
"""

from __future__ import annotations

from resume_builder.document_export import *  # noqa: F401, F403
