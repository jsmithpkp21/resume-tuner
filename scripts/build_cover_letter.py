#!/usr/bin/env python3
"""Generate a one-page cover letter for a target role/company.

Usage example:

    RESUME_BUILDER_LLM_ENABLED=1 python scripts/build_cover_letter.py \\
      --profile data/profile/profile.toml \\
      --experience-db data/experience/experience_db.toml \\
      --job-text-file /tmp/sample_jd.txt \\
      --company "Graphcore" \\
      --target-role "Senior Principal Test Framework Software Engineer" \\
      --output-dir /tmp/cover_letter_smoke \\
      --outputs pdf,docx,md,html

The cover letter is LLM-drafted; the script hard-fails when neither
``RESUME_BUILDER_LLM_ENABLED=1`` nor ``RESUME_BUILDER_LLM_FIXTURE=1``
is set. Output filenames follow the resume convention:
``<snake_case(company)>_cover_letter.{pdf,docx,html,md}``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
    from build_resume import (
        DEFAULT_EXPERIENCE_DB,
        DEFAULT_PROFILE,
        LLM_ENABLED_ENV,
        LLM_FIXTURE_ENV,
        Experience,
        Profile,
        load_experiences,
        load_independent_projects,
        load_profile,
        load_selected_achievements,
    )
    from cover_letter_export import (
        CoverLetterPageLimitError,
        render_docx,
        render_html,
        render_pdf,
    )
    from cover_letter_template import (
        CoverLetterBody,
        CoverLetterIR,
        compose_cover_letter,
        load_cover_letter_preferences,
        read_profile_payload,
        render_markdown,
    )
    from document_export import (
        canonical_export_filename,
        resolve_export_output_path,
        snake_case,
    )
    from jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from llm_client import LLMClient
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input
    from scripts.build_resume import (
        DEFAULT_EXPERIENCE_DB,
        DEFAULT_PROFILE,
        LLM_ENABLED_ENV,
        LLM_FIXTURE_ENV,
        Experience,
        Profile,
        load_experiences,
        load_independent_projects,
        load_profile,
        load_selected_achievements,
    )
    from scripts.cover_letter_export import (
        CoverLetterPageLimitError,
        render_docx,
        render_html,
        render_pdf,
    )
    from scripts.cover_letter_template import (
        CoverLetterBody,
        CoverLetterIR,
        compose_cover_letter,
        load_cover_letter_preferences,
        read_profile_payload,
        render_markdown,
    )
    from scripts.document_export import (
        canonical_export_filename,
        resolve_export_output_path,
        snake_case,
    )
    from scripts.jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from scripts.llm_client import LLMClient


logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("data/review/outputs/cover_letter")
DEFAULT_OUTPUTS: tuple[str, ...] = ("pdf", "docx")
VALID_OUTPUTS: tuple[str, ...] = ("pdf", "docx", "md", "html")
DEFAULT_ADDRESSEE_FALLBACK = "Hiring Team"
DEFAULT_WORD_BUDGET = 350
DEFAULT_ADDRESSEE_CONFIDENCE = 0.85
MAX_BULLETS_PER_EXPERIENCE = 8

ADDRESSEE_NAMESPACE = "cover_letter_addressee"
BODY_NAMESPACE = "cover_letter_body"

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_LLM_DISABLED = 2
EXIT_RENDERED_WITH_WARNINGS = 3


def _positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected integer, got {value!r}") from exc
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
    return n


def _unit_interval_float(value: str) -> float:
    try:
        x = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected float, got {value!r}") from exc
    if not (0.0 <= x <= 1.0):
        raise argparse.ArgumentTypeError(f"must be in [0.0, 1.0], got {x}")
    return x


def _parse_outputs(value: str) -> tuple[str, ...]:
    tokens = [t.strip().lower() for t in value.split(",") if t.strip()]
    if not tokens:
        raise argparse.ArgumentTypeError(
            f"--outputs requires at least one of: {', '.join(VALID_OUTPUTS)}"
        )
    invalid = [t for t in tokens if t not in VALID_OUTPUTS]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"--outputs received unknown token(s) {', '.join(invalid)}; "
            f"valid tokens: {', '.join(VALID_OUTPUTS)}"
        )
    seen: list[str] = []
    for t in tokens:
        if t not in seen:
            seen.append(t)
    return tuple(seen)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--experience-db", type=Path, default=DEFAULT_EXPERIENCE_DB)
    parser.add_argument("--job-url", type=str, default="")
    parser.add_argument(
        "--job-text-file",
        type=Path,
        default=None,
        help="Path to a plain-text file containing the full job description.",
    )
    parser.add_argument("--target-role", type=str, default="")
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help=(
            "Target company. Required when no --job-url / --job-text-file is "
            "supplied. Otherwise inferred from the JD."
        ),
    )
    parser.add_argument(
        "--hiring-manager",
        type=str,
        default=None,
        help=(
            "Address the cover letter to this person. When omitted, an LLM "
            "stage attempts to infer a hiring manager from the JD page; "
            "falls back to 'Hiring Team' otherwise."
        ),
    )
    parser.add_argument(
        "--addressee-confidence-threshold",
        type=_unit_interval_float,
        default=DEFAULT_ADDRESSEE_CONFIDENCE,
        help=(
            "Minimum self-reported LLM confidence (0.0-1.0) to accept an "
            "inferred hiring manager name. Default: %(default)s. The "
            "inferred name must also appear verbatim in the JD."
        ),
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--outputs",
        type=_parse_outputs,
        default=DEFAULT_OUTPUTS,
        help=(
            "Comma-separated artifacts to emit. Valid tokens: "
            f"{', '.join(VALID_OUTPUTS)}. Default: pdf,docx."
        ),
    )
    parser.add_argument(
        "--include-private-projects",
        action="store_true",
        help="Include private independent_projects entries as evidence.",
    )
    parser.add_argument(
        "--word-budget",
        type=_positive_int,
        default=DEFAULT_WORD_BUDGET,
        help="Soft hint to the LLM (and warning threshold). Default: %(default)s.",
    )
    parser.add_argument(
        "--enforce-page-limit",
        action="store_true",
        help="Raise instead of warn when the rendered PDF exceeds one page.",
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
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    return parser.parse_args(argv)


def _require_llm_enabled() -> None:
    """Hard-fail with a clean message when the LLM gate is closed.

    ``LLMClient.from_env()`` only honors the FIXTURE flag; the
    ``_ENABLED`` flag is checked here so disabled-LLM users get a
    deterministic error instead of a network failure.
    """
    enabled = os.getenv(LLM_ENABLED_ENV, "0").strip() == "1"
    fixture = os.getenv(LLM_FIXTURE_ENV, "0").strip() == "1"
    if enabled or fixture:
        return
    raise LLMDisabledError(
        f"Cover letter generation requires {LLM_ENABLED_ENV}=1 "
        f"(or {LLM_FIXTURE_ENV}=1 for tests). The body is LLM-drafted; "
        f"there is no offline fallback."
    )


class LLMDisabledError(RuntimeError):
    """Raised when the LLM gate is closed and we cannot draft a body."""


@dataclass(frozen=True)
class _ResolvedJD:
    job_context: JobContext | None
    full_text: str


def _ingest_job(args: argparse.Namespace) -> _ResolvedJD:
    job_url = args.job_url.strip()
    job_text_file = args.job_text_file
    if job_url and job_text_file is not None:
        raise ValueError("Provide only one of --job-url or --job-text-file")
    if job_text_file is not None:
        assert_not_blocked_runtime_input(job_text_file)
        job_text = job_text_file.read_text(encoding="utf-8")
        return _ResolvedJD(
            job_context=ingest_job_text(job_text, source_hint="job-text-file"),
            full_text=job_text,
        )
    if job_url:
        ctx = ingest_job_context(job_url)
        return _ResolvedJD(job_context=ctx, full_text=ctx.description_excerpt)
    return _ResolvedJD(job_context=None, full_text="")


def _resolve_company(args: argparse.Namespace, jd: _ResolvedJD) -> str:
    explicit = str(args.company or "").strip()
    if explicit:
        return explicit
    if jd.job_context is not None and jd.job_context.company_name.strip():
        return str(jd.job_context.company_name).strip()
    raise ValueError(
        "Cannot determine target company. Pass --company explicitly or "
        "supply a JD via --job-url / --job-text-file."
    )


def _resolve_target_role(args: argparse.Namespace, jd: _ResolvedJD) -> str:
    explicit = str(args.target_role).strip()
    if explicit:
        return explicit
    if jd.job_context is not None:
        return jd.job_context.role_hint or ""
    return ""


def _resolve_addressee(
    *,
    args: argparse.Namespace,
    jd: _ResolvedJD,
    client: LLMClient,
    fallback: str,
) -> str:
    if args.hiring_manager and str(args.hiring_manager).strip():
        return str(args.hiring_manager).strip()
    if jd.job_context is None:
        return fallback
    if jd.job_context.fetch_status == "provided_text":
        return fallback
    haystack = "\n".join([jd.job_context.page_title or "", jd.full_text or ""])
    if not haystack.strip():
        return fallback
    payload = {
        "page_title": jd.job_context.page_title or "",
        "job_description": haystack,
    }
    system_prompt = (
        "You extract the hiring manager's name from a job description page "
        "if and only if the page explicitly names one. Do not guess. "
        "Respond with strict JSON: "
        '{"hiring_manager_name": <string or null>, "confidence": <float 0..1>}. '
        "If no explicit name appears, return null and confidence 0."
    )
    try:
        result = client.complete_json(
            namespace=ADDRESSEE_NAMESPACE,
            system_prompt=system_prompt,
            user_payload=payload,
        )
    except Exception as exc:
        logger.warning("Addressee inference failed: %s", exc)
        return fallback
    name = result.get("hiring_manager_name")
    confidence = result.get("confidence", 0)
    if not isinstance(name, str) or not name.strip():
        return fallback
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value < args.addressee_confidence_threshold:
        return fallback
    if name.strip() not in haystack:
        logger.info(
            "Inferred addressee %r not present in JD text; using fallback.",
            name.strip(),
        )
        return fallback
    return name.strip()


def _experience_summary(experiences: tuple[Experience, ...]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in experiences:
        out.append(
            {
                "id": exp.id,
                "job_title": exp.job_title,
                "company": exp.company,
                "start_date": exp.start_date,
                "end_date": exp.end_date,
                "general_role_description": exp.general_role_description,
                "bullet_texts": [
                    b.text for b in exp.bullets[:MAX_BULLETS_PER_EXPERIENCE]
                ],
            }
        )
    return out


def _draft_body(
    *,
    client: LLMClient,
    profile: Profile,
    company_name: str,
    target_role: str,
    jd: _ResolvedJD,
    experiences: tuple[Experience, ...],
    selected_achievements: tuple[Any, ...],
    independent_projects: tuple[Any, ...],
    independent_projects_visible: bool,
    word_budget: int,
) -> CoverLetterBody:
    company_research = None
    if jd.job_context and jd.job_context.company_research:
        company_research = jd.job_context.company_research.to_dict()
    payload: dict[str, Any] = {
        "candidate": {
            "name": profile.name,
            "headline": profile.headline,
            "summary": profile.summary,
        },
        "target_role": target_role,
        "target_company": company_name,
        "company_research": company_research,
        "job_description": jd.full_text
        or (jd.job_context.description_excerpt if jd.job_context else ""),
        "experiences": _experience_summary(experiences),
        "selected_achievements": [a.text for a in selected_achievements],
        "independent_projects": (
            [{"name": p.name, "summary": p.summary} for p in independent_projects]
            if independent_projects_visible
            else []
        ),
        "word_budget": word_budget,
    }
    system_prompt = _BODY_SYSTEM_PROMPT
    result = client.complete_json(
        namespace=BODY_NAMESPACE,
        system_prompt=system_prompt,
        user_payload=payload,
    )
    opening = str(result.get("opening", "")).strip()
    body_paragraphs_raw = result.get("body_paragraphs", [])
    if not isinstance(body_paragraphs_raw, list):
        raise ValueError("LLM body draft missing 'body_paragraphs' list")
    body_paragraphs = tuple(
        str(p).strip() for p in body_paragraphs_raw if str(p).strip()
    )
    closing_paragraph = str(result.get("closing_paragraph", "")).strip()
    if not opening or not body_paragraphs or not closing_paragraph:
        raise ValueError(
            "LLM body draft missing one of opening / body_paragraphs / closing_paragraph"
        )
    return CoverLetterBody(
        opening=opening,
        body_paragraphs=body_paragraphs,
        closing_paragraph=closing_paragraph,
    )


_BODY_SYSTEM_PROMPT = """You draft a professional cover letter body for a software engineering role.

HARD RULES — violating any of these is a failure:
1. Use only facts present in the user payload. Do not invent metrics, team sizes, dollar amounts, percentages, dates, or achievements that are not supplied.
2. Reference experience only by what appears in `experiences`, `selected_achievements`, or `independent_projects` — paraphrasing is fine; fabrication is not.
3. Reference the target company by name (`target_company`). The cover letter is the only place company-specific framing belongs.
4. Write in first person, professional, direct. No "As an AI", no "large language model", no "I cannot", no "I'm sorry".
5. Stay near `word_budget` words across all paragraphs combined (soft hint; quality matters more than exact count, but do not exceed the budget by more than 15%).
6. If the candidate's `headline` reflects a lower level than the `target_role` (e.g., Senior Staff vs. Senior Principal), include exactly one sentence in the opening or first body paragraph framing the transition by scope/breadth/years. If headlines align, omit any gap framing entirely.

OUTPUT — strict JSON only, no prose around it:
{
  "opening": "<one paragraph: hook + role/company + (optional) one-sentence level-gap framing>",
  "body_paragraphs": ["<paragraph 1>", "<paragraph 2>", ...],
  "closing_paragraph": "<one short paragraph: call to action, thanks>"
}

Aim for 1–3 body paragraphs. Keep paragraphs tight (3–5 sentences each).
"""


def _emit_outputs(
    *,
    ir: CoverLetterIR,
    args: argparse.Namespace,
    company_name: str,
) -> tuple[list[Path], list[str]]:
    outputs = args.outputs
    output_dir: Path = args.output_dir
    output_dir = output_dir.resolve(strict=False)
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    warnings: list[str] = []

    md_text = render_markdown(ir)

    if "md" in outputs:
        md_path = output_dir / canonical_export_filename(
            company_name, "md", kind="cover_letter"
        )
        md_path.write_text(md_text, encoding="utf-8")
        written.append(md_path)

    if "html" in outputs:
        html_path = output_dir / canonical_export_filename(
            company_name, "html", kind="cover_letter"
        )
        html_path.write_text(render_html(ir), encoding="utf-8")
        written.append(html_path)

    if "docx" in outputs:
        docx_path = resolve_export_output_path(
            output_dir,
            filename_override=args.docx_filename,
            default_name=canonical_export_filename(
                company_name, "docx", kind="cover_letter"
            ),
            flag_name="--docx-filename",
        )
        render_docx(ir, docx_path)
        written.append(docx_path)

    if "pdf" in outputs:
        pdf_path = resolve_export_output_path(
            output_dir,
            filename_override=args.pdf_filename,
            default_name=canonical_export_filename(
                company_name, "pdf", kind="cover_letter"
            ),
            flag_name="--pdf-filename",
        )
        try:
            render_pdf(
                ir,
                pdf_path,
                enforce_page_limit=args.enforce_page_limit,
            )
        except CoverLetterPageLimitError:
            raise
        written.append(pdf_path)

    word_count = ir.word_count()
    if word_count > args.word_budget:
        warnings.append(
            f"Body word count {word_count} exceeds budget {args.word_budget}"
        )

    return written, warnings


def run_pipeline_collecting_paths(
    args: argparse.Namespace,
) -> tuple[list[Path], list[str]]:
    """Run the cover-letter pipeline and return (written_paths, warnings).

    Used by both ``run_pipeline`` (for the standalone CLI's stdout summary
    + exit code) and ``scripts.cover_letter.generate_cover_letter`` (for
    the resume-orchestrated path that needs the file list).
    """
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    profile = load_profile(args.profile)
    profile_payload = read_profile_payload(args.profile)
    preferences = load_cover_letter_preferences(profile_payload)

    experiences = load_experiences(args.experience_db)
    selected_achievements = load_selected_achievements(
        args.experience_db, experiences=experiences
    )
    independent_projects, ip_visibility = load_independent_projects(
        args.experience_db, experiences=experiences
    )
    ip_visible = ip_visibility == "public" or args.include_private_projects

    _require_llm_enabled()

    jd = _ingest_job(args)
    company = _resolve_company(args, jd)
    target_role = _resolve_target_role(args, jd)

    client = LLMClient.from_env()

    addressee = _resolve_addressee(
        args=args,
        jd=jd,
        client=client,
        fallback=preferences.addressee_fallback,
    )

    body = _draft_body(
        client=client,
        profile=profile,
        company_name=company,
        target_role=target_role,
        jd=jd,
        experiences=experiences,
        selected_achievements=selected_achievements,
        independent_projects=independent_projects,
        independent_projects_visible=ip_visible,
        word_budget=args.word_budget,
    )

    ir = compose_cover_letter(
        profile=profile,
        addressee=addressee,
        company_name=company,
        body=body,
        preferences=preferences,
    )

    company_slug = snake_case(company)
    written, warnings = _emit_outputs(ir=ir, args=args, company_name=company)

    summary = {
        "company": company,
        "company_slug": company_slug,
        "addressee": addressee,
        "target_role": target_role,
        "word_count": ir.word_count(),
        "word_budget": args.word_budget,
        "outputs": [str(p) for p in written],
        "warnings": warnings,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))

    return written, warnings


def run_pipeline(args: argparse.Namespace) -> int:
    _written, warnings = run_pipeline_collecting_paths(args)
    return EXIT_RENDERED_WITH_WARNINGS if warnings else EXIT_SUCCESS


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_pipeline(args)
    except LLMDisabledError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LLM_DISABLED
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
