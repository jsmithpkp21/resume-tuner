"""Cover-letter generation entry point used by build_resume's --cover-letter flag.

Delegates to ``scripts.build_cover_letter.run_pipeline_collecting_paths``
(the standalone CLI's core), supplying an argparse Namespace built from
the resume CLI's own args. Returns the list of paths actually written so
``build_resume`` can register them for staging output.

For finer control (word budget, hiring manager override, addressee
confidence threshold, custom output filenames), invoke
``scripts/build_cover_letter.py`` directly instead of going through
``build_resume.py --cover-letter``.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def generate_cover_letter(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    company: str,
    role: str,
) -> list[Path]:
    """Run the v1 cover-letter pipeline and return the paths it wrote."""
    # Imported lazily: build_cover_letter imports back from build_resume
    # (for shared loaders like load_profile / load_experiences), so a
    # module-level import here would create a circular dependency at the
    # point where build_resume itself imports this module.
    if __package__ in {None, ""}:
        import build_cover_letter as _cl
    else:
        from scripts import build_cover_letter as _cl

    output_dir.mkdir(parents=True, exist_ok=True)
    # Honor build_resume's --outputs filter so the cover letter and resume
    # share the same artifact set. Both surfaces define the same valid
    # tokens (pdf, docx, md, html), so a direct pass-through is safe.
    # Default only when the attribute is missing (older callers) — an
    # explicit empty selection is forwarded as-is so the downstream
    # pipeline behaves the same as the standalone CLI.
    outputs_attr = getattr(args, "outputs", None)
    if isinstance(outputs_attr, str):
        # tuple("pdf") would silently become ("p", "d", "f") and produce
        # zero artifacts downstream. Reject str loudly instead — callers
        # should parse comma-separated input before calling.
        raise TypeError(
            "args.outputs must be an iterable of tokens (tuple/list), not str; "
            "parse comma-separated input via build_resume._parse_outputs or "
            "build_cover_letter._parse_outputs before calling."
        )
    requested_outputs = _cl.DEFAULT_OUTPUTS if outputs_attr is None else outputs_attr
    cl_ns = argparse.Namespace(
        profile=args.profile,
        experience_db=args.experience_db,
        job_url=getattr(args, "job_url", "") or "",
        job_text_file=getattr(args, "job_text_file", None),
        target_role=role or getattr(args, "target_role", "") or "",
        company=company or "",
        hiring_manager=None,
        addressee_confidence_threshold=_cl.DEFAULT_ADDRESSEE_CONFIDENCE,
        output_dir=output_dir,
        outputs=tuple(requested_outputs),
        include_private_projects=getattr(args, "include_private_projects", False),
        word_budget=_cl.DEFAULT_WORD_BUDGET,
        enforce_page_limit=False,
        pdf_filename=None,
        docx_filename=None,
        verbose=getattr(args, "verbose", False),
    )
    written: list[Path]
    _warnings: list[str]
    written, _warnings = _cl.run_pipeline_collecting_paths(cl_ns)
    return written
