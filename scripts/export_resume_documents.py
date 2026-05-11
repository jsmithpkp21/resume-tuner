"""Compatibility wrapper for ``resume_builder.export_resume_documents`` — see issue #41."""

from __future__ import annotations

from resume_builder.export_resume_documents import *  # noqa: F401, F403

if __name__ == "__main__":
    import runpy

    runpy.run_module("resume_builder.export_resume_documents", run_name="__main__")
