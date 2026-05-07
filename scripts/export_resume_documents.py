#!/usr/bin/env python3
"""Back-compat shim for DOCX/PDF resume export.

The renderer logic moved to ``scripts/document_export.py`` and the unified CLI
lives in ``scripts/build_resume.py`` (see ``--outputs``). This module remains
as a thin wrapper so existing invocations of ``python scripts/export_resume_documents.py``
keep working: it delegates the build to ``build_resume.run_pipeline`` (with
``--outputs=html,md``) and then renders DOCX+PDF using the shared helpers
re-exported below.

Full removal is tracked as a follow-up.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    import build_resume
    import document_export
else:
    from scripts import build_resume, document_export

# ---------------------------------------------------------------------------
# Back-compat re-exports.
#
# The cross-module API in ``scripts/document_export.py`` uses public (non-
# underscore) names. This shim keeps the old underscore-prefixed aliases
# pointing at the public helpers so existing imports and tests that
# monkeypatch attributes on this module (e.g. ``monkeypatch.setattr(
# export_resume_documents, "_render_docx", ...)``) keep working. New code
# should import from ``scripts.document_export`` directly.
# ---------------------------------------------------------------------------
_SKIP_LINE_RE = document_export._SKIP_LINE_RE
_BOLD_SPLIT_RE = document_export._BOLD_SPLIT_RE
_MD_LINK_RE = document_export._MD_LINK_RE
_MD_CODE_RE = document_export._MD_CODE_RE
_SKILLS_CATEGORY_RE = document_export._SKILLS_CATEGORY_RE
_HIDDEN_HTML_CLASS_TOKENS = document_export._HIDDEN_HTML_CLASS_TOKENS
_ResumeHtmlBlockParser = document_export.ResumeHtmlBlockParser
_canonical_export_filename = document_export.canonical_export_filename
_staging_path = document_export.staging_path
_resolve_export_output_path = document_export.resolve_export_output_path
_remove_stale_legacy_exports = document_export.remove_stale_legacy_exports
_require_python_docx = document_export.require_python_docx
_require_reportlab = document_export.require_reportlab
_require_calibri_pdf_fonts = document_export.require_calibri_pdf_fonts
_find_calibri_path = document_export.find_calibri_path
_find_fontconfig_font_path = document_export.find_fontconfig_font_path
_iter_html_blocks = document_export.iter_html_blocks
_iter_markdown_blocks = document_export.iter_markdown_blocks
_apply_post_layout_cleanup = document_export.apply_post_layout_cleanup
_render_docx = document_export.render_docx
_render_pdf = document_export.render_pdf
_add_rich_runs = document_export._add_rich_runs
_set_docx_font_name = document_export._set_docx_font_name
_strip_markdown_markup = document_export._strip_markdown_markup
_split_skills_category_line = document_export._split_skills_category_line
_has_single_word_wrap_tail = document_export._has_single_word_wrap_tail
_drop_tail_skill_from_category_row = document_export._drop_tail_skill_from_category_row
_normalize_inline_text = document_export._normalize_inline_text
_wrap_text_for_pdf = document_export._wrap_text_for_pdf
_wrap_skills_category_for_pdf = document_export._wrap_skills_category_for_pdf
_wrap_mixed_style_paragraph_for_pdf = (
    document_export._wrap_mixed_style_paragraph_for_pdf
)
_contains_trailing_connector_fragment = (
    document_export.contains_trailing_connector_fragment
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=build_resume.DEFAULT_PROFILE)
    parser.add_argument(
        "--experience-db", type=Path, default=build_resume.DEFAULT_EXPERIENCE_DB
    )
    parser.add_argument(
        "--skills-matrix", type=Path, default=build_resume.DEFAULT_SKILLS_MATRIX
    )
    parser.add_argument("--job-url", type=str, default="")
    parser.add_argument("--job-text-file", type=Path, default=None)
    parser.add_argument("--target-role", type=str, default="")
    parser.add_argument(
        "--company",
        type=str,
        default="company",
        help="Company slug source for canonical output names (<company>_resume.*).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=build_resume.DEFAULT_OUTPUT_DIR
    )
    parser.add_argument(
        "--processing-mode",
        choices=("raw", "processed"),
        default="processed",
        help="Use processed mode by default for submission-ready output.",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="modern",
        help="Secondary template pass-through for build pipeline consistency.",
    )
    parser.add_argument(
        "--pdf-filename",
        type=str,
        default=None,
        help="Optional PDF file name override under --output-dir.",
    )
    parser.add_argument(
        "--docx-filename",
        type=str,
        default=None,
        help="Optional DOCX file name override under --output-dir.",
    )
    parser.add_argument(
        "--allow-overflow-pdf",
        action="store_true",
        help=(
            "Keep the generated PDF even when it exceeds the default two-page "
            "submission guard. Useful for review/debug exports."
        ),
    )
    parser.add_argument(
        "--post-layout-cleanup",
        choices=("enabled", "disabled"),
        default="enabled",
        help=(
            "Apply deterministic post-layout cleanup before DOCX/PDF render. "
            "Set to 'disabled' for strict source fidelity/debug exports."
        ),
    )
    parser.add_argument(
        "--include-private-projects",
        action="store_true",
        help=(
            "Render the [independent_projects] section in DOCX/PDF outputs "
            'even when visibility="private" in experience_db.toml. Mirrors '
            "the build_resume.py flag of the same name."
        ),
    )
    return parser.parse_args()


def _resume_artifacts_dir(output_dir: Path) -> Path:
    """Resolve the resume-artifacts subdirectory under the application root."""
    subdir: str = build_resume.RESUME_OUTPUT_SUBDIR
    return Path(output_dir) / subdir


def _pipeline_markdown_path(output_dir: Path, processing_mode: str) -> Path:
    suffix = "processed" if processing_mode == "processed" else "raw"
    return _resume_artifacts_dir(output_dir) / f"latest_resume_{suffix}.md"


def _pipeline_default_html_path(args: argparse.Namespace) -> Path:
    """Return the left-justified default-template HTML path from build output."""
    output_prefix = f"latest_resume_{args.processing_mode}"
    primary_template = "modern" if args.processing_mode == "processed" else "default"
    resume_dir = _resume_artifacts_dir(Path(args.output_dir))
    if primary_template == "default":
        return resume_dir / f"{output_prefix}.html"

    secondary_template = args.template
    if secondary_template == primary_template:
        secondary_template = "default"
    if secondary_template == "default":
        secondary_prefix = f"latest_default_resume_{args.processing_mode}"
        return resume_dir / f"{secondary_prefix}.html"

    return resume_dir / f"{output_prefix}.html"


def _run_build_pipeline(args: argparse.Namespace) -> Path:
    """Delegate the build to build_resume.run_pipeline with --outputs=html,md.

    Returns the path to the rendered markdown so the existing render flow can
    pick HTML or markdown as its render source.
    """
    pipeline_args = argparse.Namespace(
        profile=args.profile,
        experience_db=args.experience_db,
        skills_matrix=args.skills_matrix,
        job_url=args.job_url,
        job_text_file=args.job_text_file,
        target_role=args.target_role,
        output_dir=args.output_dir,
        processing_mode=args.processing_mode,
        outputs=("html", "md"),
        company=getattr(args, "company", "company"),
        pdf_filename=None,
        docx_filename=None,
        allow_overflow_pdf=False,
        post_layout_cleanup=getattr(args, "post_layout_cleanup", "enabled"),
        template=args.template,
        include_private_projects=getattr(args, "include_private_projects", False),
    )
    rc = build_resume.run_pipeline(pipeline_args)
    if rc != 0:
        raise RuntimeError(f"build pipeline failed with exit code {rc}")
    md_path = _pipeline_markdown_path(args.output_dir, args.processing_mode)
    if not md_path.exists():
        raise RuntimeError(f"expected markdown output not found: {md_path}")
    return md_path


def run() -> int:
    args = parse_args()
    try:
        markdown_path = _run_build_pipeline(args)
        md_text = markdown_path.read_text(encoding="utf-8")
        render_source_text = md_text
        using_html_source = False
        html_source_path = _pipeline_default_html_path(args)
        if html_source_path.exists():
            render_source_text = html_source_path.read_text(encoding="utf-8")
            using_html_source = True
        post_layout_cleanup = getattr(args, "post_layout_cleanup", "enabled")
        if post_layout_cleanup == "enabled":
            render_source_text = _apply_post_layout_cleanup(
                render_source_text,
                args=args,
            )
        if _contains_trailing_connector_fragment(render_source_text):
            print(
                "WARNING: render source contains trailing connector fragments; "
                "review final DOCX/PDF for awkward wraps",
                file=sys.stderr,
            )
        output_dir = Path(args.output_dir)
        resume_dir = _resume_artifacts_dir(output_dir)
        docx_output = _resolve_export_output_path(
            resume_dir,
            filename_override=args.docx_filename,
            default_name=_canonical_export_filename(args.company, "docx"),
            flag_name="--docx-filename",
        )
        pdf_output = _resolve_export_output_path(
            resume_dir,
            filename_override=args.pdf_filename,
            default_name=_canonical_export_filename(args.company, "pdf"),
            flag_name="--pdf-filename",
        )
        if docx_output.resolve(strict=False) == pdf_output.resolve(strict=False):
            raise RuntimeError(
                "DOCX and PDF outputs must be different files; "
                "choose distinct --docx-filename and --pdf-filename values."
            )
        docx_output.parent.mkdir(parents=True, exist_ok=True)
        pdf_output.parent.mkdir(parents=True, exist_ok=True)

        staged_docx = _staging_path(docx_output, label="docx")
        staged_pdf = _staging_path(pdf_output, label="pdf")
        backup_docx = _staging_path(docx_output, label="docx.bak")
        backup_pdf = _staging_path(pdf_output, label="pdf.bak")
        docx_existed_before_finalize = docx_output.exists()
        pdf_existed_before_finalize = pdf_output.exists()

        try:
            _render_docx(render_source_text, staged_docx)
            _render_pdf(
                render_source_text,
                staged_pdf,
                enforce_page_limit=not args.allow_overflow_pdf,
            )

            if docx_existed_before_finalize:
                docx_output.replace(backup_docx)
            if pdf_existed_before_finalize:
                pdf_output.replace(backup_pdf)

            staged_docx.replace(docx_output)
            staged_pdf.replace(pdf_output)
        except Exception:
            staged_docx.unlink(missing_ok=True)
            staged_pdf.unlink(missing_ok=True)

            if backup_docx.exists():
                backup_docx.replace(docx_output)
            elif not docx_existed_before_finalize:
                docx_output.unlink(missing_ok=True)
            if backup_pdf.exists():
                backup_pdf.replace(pdf_output)
            elif not pdf_existed_before_finalize:
                pdf_output.unlink(missing_ok=True)
            raise
        for backup in (backup_docx, backup_pdf):
            try:
                backup.unlink(missing_ok=True)
            except OSError as _e:
                print(
                    f"WARNING: could not remove backup file {backup}: {_e}",
                    file=sys.stderr,
                )
        removed_legacy_outputs = _remove_stale_legacy_exports(
            resume_dir.resolve(strict=False), {docx_output, pdf_output}
        )
        # Migration: pre-split exports landed directly in <output-dir>; sweep
        # the root too so stale aliases from earlier runs don't persist.
        if output_dir != resume_dir:
            removed_legacy_outputs.extend(
                _remove_stale_legacy_exports(
                    output_dir.resolve(strict=False), {docx_output, pdf_output}
                )
            )
        print("Resume exports written:")
        print(f"  {docx_output}")
        print(f"  {pdf_output}")
        if removed_legacy_outputs:
            print("  removed stale legacy exports:")
            for removed_path in removed_legacy_outputs:
                print(f"    {removed_path}")
        print(f"  source markdown: {markdown_path}")
        if using_html_source:
            print(f"  source html: {html_source_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
