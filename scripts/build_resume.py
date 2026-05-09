"""Build tailored resume outputs from profile, experience, and skills inputs."""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import math
import os
import re
import sys
import textwrap
import tomllib
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass, field
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from resume_templates import TemplateContext, get_template
    from select_skills import (
        TARGET_LINES_MAX as _SKILLS_TARGET_LINES_MAX,
    )
    from select_skills import (
        TOP_N_SKILLS,
        TOP_N_SKILLS_LLM_ENABLED,
        join_skills,
        select_skills,
    )
else:
    from scripts.resume_templates import TemplateContext, get_template
    from scripts.select_skills import (
        TARGET_LINES_MAX as _SKILLS_TARGET_LINES_MAX,
    )
    from scripts.select_skills import (
        TOP_N_SKILLS,
        TOP_N_SKILLS_LLM_ENABLED,
        join_skills,
        select_skills,
    )

# Use local import when run as `python scripts/build_resume.py`,
# and package import when loaded as `scripts.build_resume`.
if __package__ in {None, ""}:
    import document_export
    from _runtime_guard import assert_not_blocked_runtime_input
    from cover_letter import generate_cover_letter
    from jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from llm_client import LLMClient
    from measurable_outcomes import (
        has_measurable_outcome as _shared_has_measurable_outcome,
    )
else:
    from scripts import document_export
    from scripts._runtime_guard import assert_not_blocked_runtime_input
    from scripts.cover_letter import generate_cover_letter
    from scripts.jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from scripts.llm_client import LLMClient
    from scripts.measurable_outcomes import (
        has_measurable_outcome as _shared_has_measurable_outcome,
    )


DEFAULT_PROFILE = Path("data/profile/profile.toml")
DEFAULT_EXPERIENCE_DB = Path("data/experience/experience_db.toml")
DEFAULT_SKILLS_MATRIX = Path("data/skills/skills_matrix.csv")
DEFAULT_OUTPUT_BASE = Path("data/outputs")
DEFAULT_OUTPUT_DIR = DEFAULT_OUTPUT_BASE / "baseline"
RESUME_OUTPUT_SUBDIR = "resumes"
COVER_LETTER_OUTPUT_SUBDIR = "cover_letters"
COMPANY_PLACEHOLDER_SLUG = "company"
# Role-level selection should not hard-cap bullets; keep all and rank by relevance.
# Final output fitting is enforced by a line-budget pass.
DEFAULT_BULLET_LINE_WIDTH = 108
DEFAULT_MAX_BULLET_LINES = 52
# Two-page vertical-extent budget in PDF rendering points. Page is 11" tall
# with 0.5" top + bottom margins (per render_pdf in scripts/document_export.py),
# so usable height per page = 11" * 72 - 2 * 36 = 720pt. Two pages = 1440pt. We
# subtract a small safety margin to absorb per-paragraph rounding plus the
# trailing 0.2pt inter-bullet gap accumulated across ~20-25 bullets.
DEFAULT_TWO_PAGE_PT_BUDGET = 1430
# Per-paragraph rendered vertical extent in PDF points. These mirror render_pdf
# (lh values + space-before adjustments) so the estimator matches the actual
# layout, not a char-width-based abstraction.
PDF_BODY_LINE_PT = 11
PDF_BULLET_LINE_PT = 12
PDF_H1_PT = 15.2
PDF_H2_PT = 21
PDF_H3_PT = 14.2
PDF_TITLE_PT = 13
PDF_HEADER_DIVIDER_PT = 16
PDF_COMPANY_LINE_BLOCK_PT = 15
DEFAULT_MAX_ACTION_WORD_OCCURRENCES = 2
DEFAULT_MIN_BULLETS_PER_EXPERIENCE = 2
EXPERIENCE_DISPLAY_RECENCY_YEARS = 15
SUMMARY_LINE_WIDTH = 72
SUMMARY_MAX_LINES = 2
SUMMARY_MAX_WORDS = 30
PROFILE_SUMMARY_LINE_WIDTH = 115
PROFILE_SUMMARY_MAX_LINES = 6
# Prevent clipped summaries from ending on dangling connectors/fragments.
_TRAILING_FRAGMENT_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "via",
    "with",
    "without",
    "focused",
}
# Calibrated from sandbox resume corpus: longest observed summary (107 words) + 5.
PROFILE_SUMMARY_MAX_WORDS = 112
PROFILE_SUMMARY_MIN_RATIO = 0.8

# Lower-bound floor for the LLM-tailored summary path. The deterministic
# generator's PROFILE_SUMMARY_MIN_RATIO * PROFILE_SUMMARY_MAX_WORDS bound
# (~90) is a *pre-fitting* candidate floor; after _fit_profile_summary_layout
# trims to PROFILE_SUMMARY_MAX_LINES the actual output is typically ~25-50
# words. Real-world LLMs (llama3.1:8b, gemma2:9b, qwen2.5:14b) produce
# 50-90-word summaries when asked for "concise paragraph" output. Holding
# them to a 90-word minimum rejects almost every LLM response and leaves
# the deterministic fallback as the dominant path. Using a sanity floor
# of 30 lets reasonable LLM output through; the real layout guardrail is
# the wrap-line check at PROFILE_SUMMARY_LINE_WIDTH later in the helper.
_LLM_SUMMARY_MIN_WORDS = 30

# fit_assessment thresholds (#272). Score is on a 0-100 scale where higher
# means stronger fit. Below the gate, --fit-narrative auto-mode fires the
# fit-narrative augmentation; tunable later if real-JD calibration shows the
# 60 cut is too tight or too loose.
_FIT_NARRATIVE_GATE_SCORE = 60

LLM_ENABLED_ENV = "RESUME_BUILDER_LLM_ENABLED"
LLM_FIXTURE_ENV = "RESUME_BUILDER_LLM_FIXTURE"
REQUIRE_JD_CONTEXT_ENV = "RESUME_BUILDER_REQUIRE_JD_CONTEXT"

# Dedicated exit code for the --require-jd-context gate so scripted /
# CI consumers can distinguish "JD ingest was empty and required" from
# any other validation/build failure. The rest of the pipeline still
# returns literal 0 / 1 values; introducing a full named-exit-code
# scheme is out of scope here.
EXIT_JD_CONTEXT_REQUIRED = 5

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Profile:
    name: str
    headline: str
    location: str
    email: str
    phone: str
    website: str
    linkedin: str
    github: str
    summary: str
    education_entries: tuple[EducationEntry, ...]
    leadership_community_entries: tuple[LeadershipCommunityEntry, ...]
    # Optional free-form seniority hint surfaced to the fit_assessment LLM
    # call (#272). Empty string when the user does not provide one — the LLM
    # then judges fit purely from experience content.
    current_level: str = ""


@dataclass(frozen=True)
class EducationEntry:
    degree: str
    institution: str
    location: str
    date_range: str
    notes: str


@dataclass(frozen=True)
class LeadershipCommunityEntry:
    title: str
    organization: str
    date_range: str
    details: str


@dataclass(frozen=True)
class CrossOrgLeadershipEntry:
    text: str
    source_bullet_ids: tuple[str, ...]


@dataclass(frozen=True)
class SelectedAchievementEntry:
    text: str
    source_bullet_ids: tuple[str, ...]


@dataclass(frozen=True)
class IndependentProjectEntry:
    name: str
    summary: str
    key_skills: tuple[str, ...]
    source_bullet_ids: tuple[str, ...]
    url: str = ""


@dataclass(frozen=True)
class Bullet:
    id: str
    text: str
    skills: tuple[str, ...]
    impact_type: str
    domain: str
    start_date: str = ""
    end_date: str = ""


@dataclass(frozen=True)
class Experience:
    id: str
    job_title: str
    company: str
    start_date: str
    end_date: str
    general_role_description: str
    related_skills: tuple[str, ...]
    bullets: tuple[Bullet, ...]
    # Render level; default keeps current behavior unchanged. When set to
    # "compressed", the renderer emits only the title + date_range + the
    # single highest-relevance bullet (issue #271). Compression never drops
    # the experience entirely — chronology is preserved.
    compression: str = "full"


@dataclass(frozen=True)
class ResumeIR:
    profile: Profile
    target_role: str
    target_company: str
    display_headline: str
    job_context: JobContext | None
    experiences: tuple[Experience, ...]
    skills_by_category: dict[str, list[str]]
    enrichment_by_bullet_id: dict[str, dict[str, object]] = field(default_factory=dict)
    cross_org_architectural_leadership: tuple[CrossOrgLeadershipEntry, ...] = field(
        default_factory=tuple
    )
    selected_achievements: tuple[SelectedAchievementEntry, ...] = field(
        default_factory=tuple
    )
    independent_projects: tuple[IndependentProjectEntry, ...] = field(
        default_factory=tuple
    )
    independent_projects_visibility: str = "private"


VALID_OUTPUT_TOKENS = ("pdf", "docx", "md", "html")
DEFAULT_OUTPUTS = ("pdf", "docx")


_TOP_SKILLS_CAP_HARD_MAX = 60

_FIT_NARRATIVE_MODES = ("auto", "on", "off")

_EXPERIENCE_MODE_AUTO = "auto"
_EXPERIENCE_MODE_ALL = "all"
_EXPERIENCE_MODE_TOP_N_PREFIX = "top-"
_EXPERIENCE_TOP_N_PATTERN = re.compile(r"^top-(\d+)$")


def _parse_experience_mode(value: str) -> str:
    """argparse type for --experience-mode.

    Accepts ``auto``, ``all``, or ``top-N`` (with N a positive integer).
    The string is canonicalized to lower-case; the literal returned is what
    downstream code compares against (e.g. ``"top-5"``).
    """
    normalized = value.strip().lower()
    if normalized in {_EXPERIENCE_MODE_AUTO, _EXPERIENCE_MODE_ALL}:
        return normalized
    match = _EXPERIENCE_TOP_N_PATTERN.match(normalized)
    if match is not None and int(match.group(1)) >= 1:
        return normalized
    raise argparse.ArgumentTypeError(
        f"--experience-mode must be 'auto', 'all', or 'top-N' with N >= 1; "
        f"got {value!r}"
    )


def _experience_mode_top_n(mode: str) -> int | None:
    """Extract N from ``top-N`` modes; returns None for non-top-N modes."""
    match = _EXPERIENCE_TOP_N_PATTERN.match(mode)
    if match is None:
        return None
    return int(match.group(1))


def _parse_fit_narrative_mode(value: str) -> str:
    """argparse type for --fit-narrative.

    Accepts only ``auto``, ``on``, or ``off`` (case-insensitive). The mode
    governs whether the resume's profile-summary block is augmented with a
    fit-narrative clause keyed off the shared fit_assessment LLM call (#272).
    """
    normalized = value.strip().lower()
    if normalized not in _FIT_NARRATIVE_MODES:
        raise argparse.ArgumentTypeError(
            f"--fit-narrative must be one of {{{', '.join(_FIT_NARRATIVE_MODES)}}}; "
            f"got {value!r}"
        )
    return normalized


def _parse_top_skills_cap(value: str) -> int:
    """argparse type for --top-skills-cap.

    Enforces ``1 <= N < 60``: a non-positive cap silently drops every skill,
    and values at or above 60 risk page overflow on the modern template
    (issue #256 documents the upper-bound rationale).
    """
    try:
        cap = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--top-skills-cap must be an integer, got {value!r}"
        ) from exc
    if cap < 1:
        raise argparse.ArgumentTypeError(
            f"--top-skills-cap must be >= 1 (got {cap}); a non-positive cap "
            "would silently drop all skills."
        )
    if cap >= _TOP_SKILLS_CAP_HARD_MAX:
        raise argparse.ArgumentTypeError(
            f"--top-skills-cap must be < {_TOP_SKILLS_CAP_HARD_MAX} (got {cap}); "
            "larger values risk page overflow on the modern template."
        )
    return cap


def _parse_outputs(value: str) -> tuple[str, ...]:
    tokens = [token.strip().lower() for token in value.split(",") if token.strip()]
    if not tokens:
        raise argparse.ArgumentTypeError(
            f"--outputs requires at least one of: {', '.join(VALID_OUTPUT_TOKENS)}"
        )
    invalid = [token for token in tokens if token not in VALID_OUTPUT_TOKENS]
    if invalid:
        raise argparse.ArgumentTypeError(
            f"--outputs received unknown token(s) {', '.join(invalid)}; "
            f"valid tokens: {', '.join(VALID_OUTPUT_TOKENS)}"
        )
    seen: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.append(token)
    return tuple(seen)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build tailored resume outputs from profile, experience, "
            "and skills inputs.\n\n"
            "Typical usage:\n"
            "  python scripts/build_resume.py --job-url <url>\n"
            "  python scripts/build_resume.py --job-url <url> --cover-letter\n\n"
            "Override flags are listed under 'Advanced' for power users / debug."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    common = parser.add_argument_group("Common (typical run)")
    advanced = parser.add_argument_group("Advanced (overrides & debug)")

    common.add_argument(
        "--job-url",
        type=str,
        default="",
        help="URL of the job description page to tailor the resume against.",
    )
    common.add_argument(
        "--job-text-file",
        type=Path,
        default=None,
        help="Path to a plain-text file containing the full job description.",
    )
    common.add_argument(
        "--target-role",
        type=str,
        default="",
        help="Internal role tailoring hint (not rendered in output).",
    )
    common.add_argument(
        "--company",
        type=str,
        default=None,
        help=(
            "Company slug source for canonical export names "
            "(<company>_resume.{pdf,docx}). When omitted and a JD is "
            "supplied (--job-url / --job-text-file), build_resume "
            "auto-derives the slug in two tiers: first the deterministic "
            "regex/heuristic in scripts/jd_ingest.py; then an LLM "
            "extraction fallback (only when RESUME_BUILDER_LLM_ENABLED=1 "
            "or fixture mode is active). If a JD is supplied and both "
            "tiers come up empty, build_resume errors out with an "
            "actionable message rather than silently writing under "
            "data/outputs/baseline/; pass --company <slug> to bypass for "
            "one-off cases. When no JD is supplied, falls back to "
            "'company' (the smoke-run / baseline path)."
        ),
    )
    common.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Application root directory. Resume artifacts are written under "
            "<output-dir>/resumes/; cover letter artifacts (when "
            "--cover-letter is set) are written under <output-dir>/cover_letters/. "
            "When omitted and a non-placeholder company slug is available "
            "(either auto-derived from --job-url/--job-text-file or supplied "
            f"via --company), defaults to {DEFAULT_OUTPUT_BASE}/<company-slug>/; "
            f"otherwise {DEFAULT_OUTPUT_DIR}/."
        ),
    )
    common.add_argument(
        "--outputs",
        type=_parse_outputs,
        default=DEFAULT_OUTPUTS,
        help=(
            "Comma-separated artifacts to emit. Valid tokens: "
            f"{', '.join(VALID_OUTPUT_TOKENS)}. Default: pdf,docx "
            "(submission-ready + editable)."
        ),
    )
    common.add_argument(
        "--processing-mode",
        choices=("raw", "processed"),
        default="processed",
        help=(
            "processed runs transform/trim/enrich/rule/select stages "
            "(submission-ready default); raw keeps canonical content "
            "unfiltered (baseline contract / debug)."
        ),
    )
    common.add_argument(
        "--cover-letter",
        dest="cover_letter",
        action="store_true",
        default=False,
        help=(
            "Also generate a tailored cover letter alongside the resume, "
            "written under <output-dir>/cover_letters/. Body is LLM-drafted "
            "(requires RESUME_BUILDER_LLM_ENABLED=1 or fixture mode); "
            "rendered as PDF + DOCX (and Markdown / HTML for review). "
            "For finer control (word budget, hiring manager override, "
            "addressee confidence threshold) use scripts/build_cover_letter.py "
            "directly."
        ),
    )
    common.add_argument(
        "--require-jd-context",
        dest="require_jd_context",
        action="store_true",
        default=False,
        help=(
            "When JD ingest produces less than "
            f"{_MIN_JD_DESCRIPTION_CHARS} characters of description, exit "
            f"non-zero (code {EXIT_JD_CONTEXT_REQUIRED}) instead of "
            "proceeding with the un-tailored baseline. The --job-url path "
            "additionally prints the existing WARNING (which describes the "
            "JS-rendered-content failure mode and the --job-text-file "
            "workaround) before the ERROR; the --job-text-file path emits "
            "only the ERROR since the diagnostic doesn't apply to user-"
            "supplied text. Useful for scripted runs where producing a "
            "generic resume would be a silent failure. Also enabled by "
            f"{REQUIRE_JD_CONTEXT_ENV}=1; either signal independently enables "
            "gating, and once enabled there is no override-down (i.e. env "
            "var = '0' does not disable an explicit --require-jd-context flag)."
        ),
    )

    advanced.add_argument(
        "--profile",
        type=Path,
        default=DEFAULT_PROFILE,
        help="Profile data source TOML.",
    )
    advanced.add_argument(
        "--experience-db",
        type=Path,
        default=DEFAULT_EXPERIENCE_DB,
        help="Experience database TOML.",
    )
    advanced.add_argument(
        "--skills-matrix",
        type=Path,
        default=DEFAULT_SKILLS_MATRIX,
        help="Skills matrix CSV.",
    )
    advanced.add_argument(
        "--pdf-filename",
        type=str,
        default=None,
        help="Optional PDF file name override under <output-dir>/resumes/.",
    )
    advanced.add_argument(
        "--docx-filename",
        type=str,
        default=None,
        help="Optional DOCX file name override under <output-dir>/resumes/.",
    )
    advanced.add_argument(
        "--allow-overflow-pdf",
        action="store_true",
        help=(
            "Keep the generated PDF even when it exceeds the default two-page "
            "submission guard. Useful for review/debug exports."
        ),
    )
    advanced.add_argument(
        "--post-layout-cleanup",
        choices=("enabled", "disabled"),
        default="enabled",
        help=(
            "Apply deterministic post-layout cleanup before DOCX/PDF render. "
            "Set to 'disabled' for strict source fidelity/debug exports."
        ),
    )
    advanced.add_argument(
        "--include-private-projects",
        action="store_true",
        help=(
            "Render the [independent_projects] section even when "
            'visibility="private" in experience_db.toml. Lets the user preview '
            "rendered output without flipping the canonical visibility flag."
        ),
    )
    advanced.add_argument(
        "--template",
        type=str,
        default="modern",
        help=(
            "Secondary HTML layout template name. Primary latest_* uses default "
            "in raw mode and modern in processed mode. If the requested secondary "
            "template matches the primary template, build_resume automatically "
            "uses the other built-in template for the secondary artifact."
        ),
    )
    advanced.add_argument(
        "--top-skills-cap",
        type=_parse_top_skills_cap,
        default=None,
        metavar="N",
        help=(
            f"Override the maximum number of skills retained across all "
            f"categories. Default: {TOP_N_SKILLS} (LLM stages disabled) or "
            f"{TOP_N_SKILLS_LLM_ENABLED} (LLM stages enabled). Accepts "
            f"1 <= N < {_TOP_SKILLS_CAP_HARD_MAX}; tunable for visual fit."
        ),
    )
    advanced.add_argument(
        "--fit-narrative",
        type=_parse_fit_narrative_mode,
        default="auto",
        metavar="auto|on|off",
        help=(
            "Whether the profile-summary block should be augmented with a "
            "fit-narrative clause when the candidate is a stretch for the "
            "JD. 'auto' (default) lets the LLM-judged fit_assessment score "
            "decide; auto-mode also defers to 'off' when --cover-letter "
            "is enabled or LLM stages are disabled. 'on' forces fire; "
            "'off' suppresses entirely. See DESIGN.md \"Fit narrative\" "
            "for the gate semantics."
        ),
    )
    advanced.add_argument(
        "--experience-mode",
        type=_parse_experience_mode,
        default="auto",
        metavar="auto|all|top-N",
        help=(
            "How experience compression is applied to low-fit roles. "
            "'auto' (default) is layout-driven: experiences render in full "
            "until the page overflows, then lowest-fit experiences "
            "(per fit_assessment) compress one at a time, capped at 50% "
            "of in-window experiences. 'all' forces every experience full. "
            "'top-N' (e.g. top-5) renders the top N by relevance + recency "
            "in full and compresses the rest, also subject to the 50% cap. "
            "Experiences are never dropped — chronology is preserved. "
            'See DESIGN.md "Experience compression".'
        ),
    )
    return parser.parse_args()


def _read_toml(path: Path) -> dict[str, Any]:
    assert_not_blocked_runtime_input(path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_profile(path: Path) -> Profile:
    try:
        payload = _read_toml(path)
    except FileNotFoundError as exc:
        raise ValueError(
            f"Profile file not found at '{path}'. "
            f"Copy data/profile/profile.example.toml to {path} and fill in real values "
            f"before running the pipeline (profile.toml is gitignored per-contributor input)."
        ) from exc
    data = payload.get("profile", {})
    if not isinstance(data, dict):
        raise ValueError("profile.toml must contain a [profile] table")

    raw_education = payload.get("education", [])
    if not isinstance(raw_education, list):
        raise ValueError("profile.toml education must use [[education]] entries")
    education_entries_raw: list[EducationEntry] = []
    for item in raw_education:
        if not isinstance(item, dict):
            raise ValueError("Each [[education]] entry must be a table")
        education_entries_raw.append(
            EducationEntry(
                degree=str(item.get("degree", "")),
                institution=str(item.get("institution", "")),
                location=str(item.get("location", "")),
                date_range=str(item.get("date_range", "")),
                notes=str(item.get("notes", "")),
            )
        )
    education_entries = tuple(education_entries_raw)

    raw_leadership = payload.get("leadership_community", [])
    if not isinstance(raw_leadership, list):
        raise ValueError(
            "profile.toml leadership/community must use [[leadership_community]] entries"
        )
    leadership_entries_raw: list[LeadershipCommunityEntry] = []
    for item in raw_leadership:
        if not isinstance(item, dict):
            raise ValueError("Each [[leadership_community]] entry must be a table")
        leadership_entries_raw.append(
            LeadershipCommunityEntry(
                title=str(item.get("title", "")),
                organization=str(item.get("organization", "")),
                date_range=str(item.get("date_range", "")),
                details=str(item.get("details", "")),
            )
        )
    leadership_community_entries = tuple(leadership_entries_raw)

    return Profile(
        name=str(data.get("name", "")),
        headline=str(data.get("headline", "")),
        location=str(data.get("location", "")),
        email=str(data.get("email", "")),
        phone=str(data.get("phone", "")),
        website=str(data.get("website", "")),
        linkedin=_normalize_linkedin_slug(str(data.get("linkedin", ""))),
        github=_normalize_github_username(str(data.get("github", ""))),
        summary=str(data.get("summary", "")),
        education_entries=education_entries,
        leadership_community_entries=leadership_community_entries,
        current_level=str(data.get("current_level", "")).strip(),
    )


def _normalize_linkedin_slug(value: str) -> str:
    """Accept slug or URL-like input, then keep only the LinkedIn /in/ slug.

    Returns an empty string for non-/in/ LinkedIn URLs (e.g. /company/) to
    avoid producing bogus profile links.
    """
    cleaned = value.strip().replace("http://", "").replace("https://", "")
    cleaned = cleaned.replace("www.", "")
    cleaned = cleaned.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if cleaned.startswith("linkedin.com/"):
        remainder = cleaned[len("linkedin.com/") :]
        if not remainder.startswith("in/"):
            return ""
        cleaned = remainder[len("in/") :]
    elif cleaned.startswith("in/"):
        cleaned = cleaned[len("in/") :]
    cleaned = cleaned.strip().strip("/")
    return cleaned.split("/", maxsplit=1)[0].strip()


def _normalize_github_username(value: str) -> str:
    """Accept username or URL-like input, then keep only the GitHub username.

    Returns an empty string for GitHub-adjacent hosts (e.g. gist.github.com)
    that do not map to a user profile URL.
    """
    cleaned = value.strip().replace("http://", "").replace("https://", "")
    cleaned = cleaned.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if cleaned.startswith("www.github.com/"):
        cleaned = cleaned[len("www.github.com/") :]
    elif cleaned.startswith("github.com/"):
        cleaned = cleaned[len("github.com/") :]
    elif "github.com" in cleaned:
        # Adjacent host (e.g. gist.github.com) – reject to avoid malformed link.
        return ""
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    cleaned = cleaned.strip().strip("/")
    return cleaned.split("/", maxsplit=1)[0].strip()


def _build_linkedin_url(slug: str) -> str:
    if not slug.strip():
        return ""
    return f"linkedin.com/in/{slug.strip()}"


def _build_github_url(username: str) -> str:
    if not username.strip():
        return ""
    return f"github.com/{username.strip()}"


def resolve_headline(profile: Profile, target_role: str) -> str:
    """Return profile headline for rendering.

    target_role is an internal tailoring hint and must not appear in resume output.
    """
    del target_role
    return profile.headline


def _normalize_role_acronyms(text: str) -> str:
    """Normalize role acronyms while preserving casing for output."""
    # Replace SDET and QA variants, preserving the case structure
    normalized = re.sub(r"\bsdet\b", "SDET", text, flags=re.IGNORECASE)
    normalized = re.sub(r"\bqa\b", "QA", normalized, flags=re.IGNORECASE)
    return normalized


def _get_base_role(resume: ResumeIR) -> str:
    """Extract base role label from role-hint/target-role first, not rendered title.

    Uses the priority: target_role > job_context.role_hint > display_headline > profile_headline
    This ensures summaries use the original role input, not a formatted/derived version.
    """
    # Priority 1: explicit target_role parameter
    target_role = resume.target_role.strip()
    if target_role:
        base = target_role
        if "|" in base:
            base = base.split("|", maxsplit=1)[0].strip()
        return " ".join(base.split())

    # Priority 2: job context role_hint (if available)
    if resume.job_context is not None:
        role_hint = str(resume.job_context.role_hint).strip()
        if role_hint:
            if "|" in role_hint:
                role_hint = role_hint.split("|", maxsplit=1)[0].strip()
            return " ".join(role_hint.split())

    # Priority 3: display_headline
    headline = resume.display_headline.strip()
    if headline:
        if "|" in headline:
            headline = headline.split("|", maxsplit=1)[0].strip()
        return " ".join(headline.split())

    # Fallback: profile headline
    profile_headline = resume.profile.headline.strip()
    if profile_headline:
        if "|" in profile_headline:
            profile_headline = profile_headline.split("|", maxsplit=1)[0].strip()
        return " ".join(profile_headline.split())

    return ""


def derive_resume_title(resume: ResumeIR) -> str:
    """Derive resume title from the tracked profile headline only.

    Never fall back to target-role or job-context hints for visible output.
    """

    profile_headline = " ".join(resume.profile.headline.strip().split())
    if profile_headline:
        normalized = re.sub(r"\s*\|\s*", " / ", profile_headline)
        normalized = " ".join(normalized.split())
        return _normalize_role_acronyms(normalized)

    return "Software Test Automation Engineer"


def load_experiences(path: Path) -> tuple[Experience, ...]:
    payload = _read_toml(path)
    raw_experiences = payload.get("experience", [])
    if not isinstance(raw_experiences, list):
        raise ValueError("experience_db.toml must contain [[experience]] entries")

    experiences: list[Experience] = []
    seen_experience_ids: set[str] = set()
    for item in raw_experiences:
        if not isinstance(item, dict):
            raise ValueError("Each [[experience]] entry must be a table")

        raw_bullets = item.get("bullet_bank", [])
        if not isinstance(raw_bullets, list):
            raise ValueError("experience.bullet_bank must be a list")

        raw_related_skills = item.get("related_skills", [])
        if not isinstance(raw_related_skills, list):
            raise ValueError("experience.related_skills must be a list")

        bullets: list[Bullet] = []
        role_start_date = str(item.get("start_date", "")).strip()
        role_end_date = str(item.get("end_date", "")).strip()
        for raw_bullet in raw_bullets:
            if not isinstance(raw_bullet, dict):
                raise ValueError("Each bullet_bank entry must be a table")
            raw_skills = raw_bullet.get("skills", [])
            if not isinstance(raw_skills, list):
                raise ValueError("bullet_bank.skills must be a list")
            bullets.append(
                Bullet(
                    id=str(raw_bullet.get("id", "")),
                    text=str(raw_bullet.get("text", "")),
                    skills=tuple(str(skill) for skill in raw_skills),
                    impact_type=str(raw_bullet.get("impact_type", "")),
                    domain=str(raw_bullet.get("domain", "")),
                    start_date=str(raw_bullet.get("start_date", "")).strip()
                    or role_start_date,
                    end_date=str(raw_bullet.get("end_date", "")).strip()
                    or role_end_date,
                )
            )

        experience_id = str(item.get("id", "")).strip()
        # apply_experience_compression and other render-time helpers track
        # experiences by id; empty / duplicate ids would silently bucket
        # multiple roles together. Fail loud at load instead.
        if not experience_id:
            raise ValueError(
                "experience_db.toml [[experience]] entries must have a non-empty id; "
                f"missing id near job_title={item.get('job_title', '')!r}"
            )
        if experience_id in seen_experience_ids:
            raise ValueError(
                "experience_db.toml [[experience]] ids must be unique; "
                f"duplicate id={experience_id!r}"
            )
        seen_experience_ids.add(experience_id)
        experiences.append(
            Experience(
                id=experience_id,
                job_title=str(item.get("job_title", "")),
                company=str(item.get("company", "")),
                start_date=role_start_date,
                end_date=role_end_date,
                general_role_description=str(item.get("general_role_description", "")),
                related_skills=tuple(str(skill) for skill in raw_related_skills),
                bullets=tuple(bullets),
            )
        )

    return tuple(experiences)


def load_cross_org_architectural_leadership(
    path: Path,
    *,
    experiences: tuple[Experience, ...],
) -> tuple[CrossOrgLeadershipEntry, ...]:
    payload = _read_toml(path)
    section = payload.get("cross_org_architectural_leadership", {})
    if not isinstance(section, dict):
        raise ValueError("cross_org_architectural_leadership must be a table")

    raw_items = section.get("items", [])
    if raw_items in (None, ""):
        return ()
    if not isinstance(raw_items, list):
        raise ValueError(
            "cross_org_architectural_leadership.items must use [[...items]] entries"
        )

    known_bullet_ids = {
        bullet.id for experience in experiences for bullet in experience.bullets
    }
    entries: list[CrossOrgLeadershipEntry] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError(
                "Each [[cross_org_architectural_leadership.items]] entry must be a table"
            )
        text = str(item.get("text", "")).strip()
        raw_ids = item.get("source_bullet_ids", [])
        if not isinstance(raw_ids, list):
            raise ValueError(
                "cross_org_architectural_leadership.items.source_bullet_ids must be a list"
            )
        source_ids = tuple(
            str(value).strip() for value in raw_ids if str(value).strip()
        )
        unknown = sorted(
            source_id for source_id in source_ids if source_id not in known_bullet_ids
        )
        if unknown:
            raise ValueError(
                "Unknown cross_org_architectural_leadership source_bullet_ids: "
                + ", ".join(unknown)
            )
        if text:
            entries.append(
                CrossOrgLeadershipEntry(text=text, source_bullet_ids=source_ids)
            )
    return tuple(entries)


def load_selected_achievements(
    path: Path,
    *,
    experiences: tuple[Experience, ...],
) -> tuple[SelectedAchievementEntry, ...]:
    payload = _read_toml(path)
    section = payload.get("selected_achievements", {})
    if not isinstance(section, dict):
        raise ValueError("selected_achievements must be a table")

    raw_items = section.get("items", [])
    if raw_items in (None, ""):
        return ()
    if not isinstance(raw_items, list):
        raise ValueError("selected_achievements.items must use [[...items]] entries")

    known_bullet_ids = {
        bullet.id for experience in experiences for bullet in experience.bullets
    }
    entries: list[SelectedAchievementEntry] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError(
                "Each [[selected_achievements.items]] entry must be a table"
            )
        text = str(item.get("text", "")).strip()
        raw_ids = item.get("source_bullet_ids", [])
        if not isinstance(raw_ids, list):
            raise ValueError(
                "selected_achievements.items.source_bullet_ids must be a list"
            )
        source_ids = tuple(
            str(value).strip() for value in raw_ids if str(value).strip()
        )
        unknown = sorted(
            source_id for source_id in source_ids if source_id not in known_bullet_ids
        )
        if unknown:
            raise ValueError(
                "Unknown selected_achievements source_bullet_ids: " + ", ".join(unknown)
            )
        if text:
            entries.append(
                SelectedAchievementEntry(text=text, source_bullet_ids=source_ids)
            )

    return tuple(entries)


_INDEPENDENT_PROJECTS_VALID_VISIBILITY = ("public", "private")


def _normalize_independent_project_url(raw: str) -> str:
    """Return a safe http/https URL or empty string.

    - If the input has no scheme (e.g. ``github.com/org/repo``), prepend
      ``https://`` so authors can write bare domains.
    - If the apparent "scheme" contains a dot (e.g. ``github.com:8443/org/repo``
      which :func:`urllib.parse.urlsplit` parses as scheme ``github.com``),
      treat it as a bare domain:port pattern and prepend ``https://``.
    - If the scheme is anything other than ``http`` / ``https``
      (e.g. ``javascript:``, ``data:``, ``ftp:``), drop the URL entirely
      to keep generated HTML safe.
    - After normalization, reject URLs with an empty netloc (e.g. ``http://``)
      to avoid passing malformed inputs to the HTML renderer.
    """
    candidate = raw.strip()
    if not candidate:
        return ""
    parsed = urllib.parse.urlsplit(candidate)
    scheme = parsed.scheme.lower()
    # Real RFC 3986 schemes never contain a dot; if urlsplit produces a scheme
    # with a dot it has mistakenly parsed a bare hostname (e.g. "github.com" in
    # "github.com:8443/org/repo") as the scheme component.
    if not scheme or "." in scheme:
        normalized = f"https://{candidate}"
    elif scheme in ("http", "https"):
        normalized = candidate
    else:
        return ""
    # Guard against malformed inputs like "http://" that have a valid scheme
    # but an empty netloc; such strings would produce broken anchor tags.
    if not urllib.parse.urlsplit(normalized).netloc:
        return ""
    return normalized


def load_independent_projects(
    path: Path,
    *,
    experiences: tuple[Experience, ...],
) -> tuple[tuple[IndependentProjectEntry, ...], str]:
    payload = _read_toml(path)
    section = payload.get("independent_projects", {})
    if not isinstance(section, dict):
        raise ValueError("independent_projects must be a table")

    visibility_raw = section.get("visibility", "private")
    visibility = str(visibility_raw).strip().lower()
    if visibility not in _INDEPENDENT_PROJECTS_VALID_VISIBILITY:
        raise ValueError(
            "independent_projects.visibility must be one of: "
            + ", ".join(_INDEPENDENT_PROJECTS_VALID_VISIBILITY)
        )

    raw_items = section.get("items", [])
    if raw_items in (None, ""):
        return (), visibility
    if not isinstance(raw_items, list):
        raise ValueError("independent_projects.items must use [[...items]] entries")

    known_bullet_ids = {
        bullet.id for experience in experiences for bullet in experience.bullets
    }
    entries: list[IndependentProjectEntry] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError(
                "Each [[independent_projects.items]] entry must be a table"
            )
        name = str(item.get("name", "")).strip()
        summary = str(item.get("summary", "")).strip()
        url = _normalize_independent_project_url(str(item.get("url", "")))

        raw_skills = item.get("key_skills", [])
        if not isinstance(raw_skills, list):
            raise ValueError("independent_projects.items.key_skills must be a list")
        key_skills = tuple(
            str(value).strip() for value in raw_skills if str(value).strip()
        )

        raw_ids = item.get("source_bullet_ids", [])
        if not isinstance(raw_ids, list):
            raise ValueError(
                "independent_projects.items.source_bullet_ids must be a list"
            )
        source_ids = tuple(
            str(value).strip() for value in raw_ids if str(value).strip()
        )
        unknown = sorted(
            source_id for source_id in source_ids if source_id not in known_bullet_ids
        )
        if unknown:
            raise ValueError(
                "Unknown independent_projects source_bullet_ids: " + ", ".join(unknown)
            )
        if name:
            entries.append(
                IndependentProjectEntry(
                    name=name,
                    summary=summary,
                    key_skills=key_skills,
                    source_bullet_ids=source_ids,
                    url=url,
                )
            )

    return tuple(entries), visibility


def load_skills_by_category(path: Path) -> dict[str, list[str]]:
    assert_not_blocked_runtime_input(path)
    skills_by_category: dict[str, list[str]] = {}

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            skill = (row.get("Skills") or "").strip()
            category = (row.get("Category") or "").strip()
            if not skill or not category:
                continue
            skills_by_category.setdefault(category, []).append(skill)

    return skills_by_category


def assemble_baseline_resume(
    *,
    profile: Profile,
    target_role: str,
    target_company: str,
    job_context: JobContext | None,
    experiences: tuple[Experience, ...],
    skills_by_category: dict[str, list[str]],
    cross_org_architectural_leadership: tuple[CrossOrgLeadershipEntry, ...] = (),
    selected_achievements: tuple[SelectedAchievementEntry, ...] = (),
    independent_projects: tuple[IndependentProjectEntry, ...] = (),
    independent_projects_visibility: str = "private",
) -> ResumeIR:
    """Assemble baseline IR with unchanged canonical content."""
    return ResumeIR(
        profile=profile,
        target_role=target_role,
        target_company=target_company,
        display_headline=resolve_headline(profile, target_role),
        job_context=job_context,
        experiences=experiences,
        skills_by_category=skills_by_category,
        enrichment_by_bullet_id={},
        cross_org_architectural_leadership=cross_org_architectural_leadership,
        selected_achievements=selected_achievements,
        independent_projects=independent_projects,
        independent_projects_visibility=independent_projects_visibility,
    )


def transform_for_role(resume: ResumeIR) -> ResumeIR:
    """Rewrite bullet text to better match the target role without changing facts.

    Purpose:
        Adapt tone, framing, and emphasis of each bullet to the target role's
        job description signals. This is the only current pre-layout stage that
        rewrites bullet text.

    Allowed:
        - Rewrite bullet text (tone, phrasing, keyword alignment).
        - Adapt framing to match JD terminology and role context.

    Not allowed:
        - Add facts or metrics not present in the original bullet.
        - Select, reorder, or remove bullets.
        - Change bullet IDs or metadata fields.

    Future note:
        A later layout-aware pass may still shorten wording after actual page-fit
        measurement when targeting constrained formats such as PDF or DOCX.
    """
    if resume.job_context is None:
        return resume
    if (
        not resume.job_context.description_excerpt.strip()
        and not resume.target_role.strip()
    ):
        return resume
    if not _llm_stage_enabled():
        return resume

    try:
        client = LLMClient.from_env()
        transformed_experiences = tuple(
            _transform_experience_bullets(
                client=client,
                resume=resume,
                experience=experience,
            )
            for experience in resume.experiences
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("transform_for_role fallback to baseline: %s", exc)
        return resume

    return ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=transformed_experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=resume.enrichment_by_bullet_id,
        cross_org_architectural_leadership=resume.cross_org_architectural_leadership,
        selected_achievements=resume.selected_achievements,
        independent_projects=resume.independent_projects,
        independent_projects_visibility=resume.independent_projects_visibility,
    )


def _transform_experience_bullets(
    *,
    client: LLMClient,
    resume: ResumeIR,
    experience: Experience,
) -> Experience:
    """Apply LLM rewrites to bullet text for a single experience; fall back to originals."""
    rewrites = _rewrite_experience_bullets(
        client=client, resume=resume, experience=experience
    )
    if not rewrites:
        return experience

    new_bullets: list[Bullet] = []
    changed = False
    for bullet in experience.bullets:
        rewritten_text = _normalize_transformed_bullet_text(
            original_text=bullet.text,
            rewritten_text=rewrites.get(bullet.id, ""),
        )
        if rewritten_text and rewritten_text != bullet.text:
            new_bullets.append(
                Bullet(
                    id=bullet.id,
                    text=rewritten_text,
                    skills=bullet.skills,
                    impact_type=bullet.impact_type,
                    domain=bullet.domain,
                    start_date=bullet.start_date,
                    end_date=bullet.end_date,
                )
            )
            changed = True
        else:
            new_bullets.append(bullet)

    if not changed:
        return experience

    return Experience(
        id=experience.id,
        job_title=experience.job_title,
        company=experience.company,
        start_date=experience.start_date,
        end_date=experience.end_date,
        general_role_description=experience.general_role_description,
        related_skills=experience.related_skills,
        bullets=tuple(new_bullets),
    )


def _rewrite_experience_bullets(
    *, client: LLMClient, resume: ResumeIR, experience: Experience
) -> dict[str, str]:
    """Call LLM to rewrite bullets for a single experience; return id→rewritten_text map."""
    if resume.job_context is None:
        return {}

    role_hint = resume.target_role.strip() or resume.job_context.role_hint
    company_hint = resume.target_company.strip() or resume.job_context.company_name
    bullet_payload = [
        {"id": bullet.id, "text": bullet.text, "skills": list(bullet.skills)}
        for bullet in experience.bullets
    ]

    response_payload = client.complete_json(
        namespace="transform_for_role",
        system_prompt=(
            "You are rewriting resume bullets to better match a target role. "
            "Preserve all factual claims, metrics, technologies, and chronology exactly. "
            "Keep a direct engineering tone and make minimal edits; avoid generic hype phrasing. "
            "Keep sentence case and proper capitalization. "
            "Do not use first-person voice. "
            "Prefer small wording shifts over full rewrites. "
            "Return JSON only with key: bullets."
        ),
        user_payload={
            "target_role": role_hint,
            "target_company": company_hint,
            "job_description_excerpt": resume.job_context.description_excerpt,
            "experience": {
                "id": experience.id,
                "job_title": experience.job_title,
                "company": experience.company,
                "role_summary": experience.general_role_description,
            },
            "bullets": bullet_payload,
            "response_schema": {
                "bullets": [
                    {
                        "id": "<bullet-id>",
                        "rewritten_text": "<rewritten bullet text>",
                    }
                ]
            },
        },
    )

    raw_bullets = response_payload.get("bullets", [])
    if not isinstance(raw_bullets, list):
        return {}

    known_ids = {bullet.id for bullet in experience.bullets}
    parsed: dict[str, str] = {}
    for item in raw_bullets:
        if not isinstance(item, dict):
            continue
        bullet_id = str(item.get("id", "")).strip()
        if not bullet_id or bullet_id not in known_ids:
            continue
        rewritten = str(item.get("rewritten_text", "")).strip()
        if rewritten:
            parsed[bullet_id] = rewritten
    return parsed


_FIRST_PERSON_PATTERN = re.compile(r"\b(i|me|my|mine|we|us|our|ours)\b", re.IGNORECASE)
_GENERIC_HYPE_PHRASES = (
    "demonstrated strong",
    "proven track record",
    "results-driven",
    "dynamic professional",
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+/#-]*")
_GAP_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9+/#.-]*")
_GAP_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def _normalize_transformed_bullet_text(
    *, original_text: str, rewritten_text: str
) -> str:
    """Apply deterministic surface fixes and reject low-quality rewrite drift."""
    rewritten = " ".join(rewritten_text.split()).strip()
    if not rewritten:
        return ""

    # Preserve sentence-start casing style from canonical text.
    original = original_text.strip()
    if (
        original
        and original[0].isalpha()
        and original[0].isupper()
        and rewritten[0].isalpha()
        and rewritten[0].islower()
    ):
        rewritten = rewritten[0].upper() + rewritten[1:]

    # Keep terminal punctuation style stable when source has explicit punctuation.
    if original and original[-1] in ".!?" and rewritten[-1] not in ".!?":
        rewritten = f"{rewritten}{original[-1]}"

    if not _passes_transform_guardrails(
        original_text=original_text, rewritten_text=rewritten
    ):
        return ""
    return rewritten


def _passes_transform_guardrails(*, original_text: str, rewritten_text: str) -> bool:
    """Reject rewrites that drift too far from source voice/details."""
    lowered = rewritten_text.lower()
    if "!" in rewritten_text:
        return False
    if _FIRST_PERSON_PATTERN.search(rewritten_text):
        return False
    if any(phrase in lowered for phrase in _GENERIC_HYPE_PHRASES):
        return False

    original_len = max(1, len(original_text.strip()))
    rewritten_len = len(rewritten_text.strip())
    length_ratio = rewritten_len / original_len
    if length_ratio < 0.6 or length_ratio > 1.45:
        return False

    original_tokens = {
        token.lower()
        for token in _TOKEN_PATTERN.findall(original_text)
        if len(token) >= 4
    }
    if not original_tokens:
        return True
    rewritten_tokens = {
        token.lower()
        for token in _TOKEN_PATTERN.findall(rewritten_text)
        if len(token) >= 4
    }
    overlap = len(original_tokens & rewritten_tokens) / len(original_tokens)
    return overlap >= 0.35


def trim_for_role(resume: ResumeIR) -> ResumeIR:
    """Rank bullets by role relevance without removing or rewriting them.

    Purpose:
        Reorder each experience's bullets by descending LLM relevance score so
        that downstream line-budget trimming (trim_by_rules) removes the
        lowest-signal bullets first.

    Allowed:
        - Reorder bullets within each experience by descending relevance.

    Not allowed:
        - Remove bullets (that is trim_by_rules' responsibility).
        - Rewrite bullet text.
        - Edit canonical source data.
    """
    if resume.job_context is None:
        return resume
    if (
        not resume.job_context.description_excerpt.strip()
        and not resume.target_role.strip()
    ):
        return resume
    if not _llm_stage_enabled():
        return resume

    try:
        client = LLMClient.from_env()
        trimmed_experiences = tuple(
            _rank_experience_bullets(
                client=client,
                resume=resume,
                experience=experience,
            )
            for experience in resume.experiences
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trim_for_role fallback to baseline: %s", exc)
        return resume

    return ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=trimmed_experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=resume.enrichment_by_bullet_id,
        cross_org_architectural_leadership=resume.cross_org_architectural_leadership,
        selected_achievements=resume.selected_achievements,
        independent_projects=resume.independent_projects,
        independent_projects_visibility=resume.independent_projects_visibility,
    )


def _rank_experience_bullets(
    *,
    client: LLMClient,
    resume: ResumeIR,
    experience: Experience,
) -> Experience:
    """Reorder bullets by descending relevance score; all bullets are kept.

    Selection/removal of low-priority bullets is handled downstream by trim_by_rules.
    """
    if len(experience.bullets) <= 1:
        return experience

    scores = _score_bullet_relevance(
        client=client, resume=resume, experience=experience
    )
    if not scores:
        return experience

    # Emit full per-bullet score map before ranking for audit/debug tracing.
    score_map = {
        bullet.id: _coerce_relevance_score(scores.get(bullet.id))
        for bullet in experience.bullets
    }
    logger.debug(
        "trim_for_role scores experience_id=%s score_map=%s",
        experience.id,
        score_map,
    )

    ranked_pairs: list[tuple[int, Bullet]] = sorted(
        enumerate(experience.bullets),
        key=lambda pair: (-scores.get(pair[1].id, 0.0), pair[0]),
    )
    trimmed = tuple(bullet for _, bullet in ranked_pairs)

    return Experience(
        id=experience.id,
        job_title=experience.job_title,
        company=experience.company,
        start_date=experience.start_date,
        end_date=experience.end_date,
        general_role_description=experience.general_role_description,
        related_skills=experience.related_skills,
        bullets=trimmed,
    )


def _score_bullet_relevance(
    *, client: LLMClient, resume: ResumeIR, experience: Experience
) -> dict[str, float]:
    bullet_payload = [
        {"id": bullet.id, "text": bullet.text, "skills": list(bullet.skills)}
        for bullet in experience.bullets
    ]
    if resume.job_context is None:
        return {}
    role_hint = resume.target_role.strip() or resume.job_context.role_hint
    company_hint = resume.target_company.strip() or resume.job_context.company_name

    response_payload = client.complete_json(
        namespace="trim_for_role",
        system_prompt=(
            "You are ranking resume bullets for role relevance. "
            "Return JSON only with keys: scores."
        ),
        user_payload={
            "target_role": role_hint,
            "target_company": company_hint,
            "job_description_excerpt": resume.job_context.description_excerpt,
            "experience": {
                "id": experience.id,
                "job_title": experience.job_title,
                "company": experience.company,
                "role_summary": experience.general_role_description,
            },
            "bullets": bullet_payload,
            "response_schema": {
                "scores": [
                    {
                        "id": "<bullet-id>",
                        "score": "<float between 0.0 and 1.0>",
                    }
                ]
            },
        },
    )

    raw_scores = response_payload.get("scores", [])
    if not isinstance(raw_scores, list):
        return {}

    parsed_scores: dict[str, float] = {}
    for item in raw_scores:
        if not isinstance(item, dict):
            continue
        bullet_id = str(item.get("id", "")).strip()
        if not bullet_id:
            continue
        parsed_scores[bullet_id] = _coerce_relevance_score(item.get("score"))
    return _apply_measurable_outcome_boost(experience=experience, scores=parsed_scores)


def _has_measurable_outcome(text: str) -> bool:
    """Compatibility wrapper for shared measurable-outcome detection."""
    return bool(_shared_has_measurable_outcome(text))


def _apply_measurable_outcome_boost(
    *, experience: Experience, scores: dict[str, float]
) -> dict[str, float]:
    """Boost bullets with measurable outcomes so high-signal evidence sorts earlier."""
    boosted: dict[str, float] = dict(scores)
    for bullet in experience.bullets:
        base_score = boosted.get(bullet.id, 0.0)
        if _has_measurable_outcome(bullet.text):
            boosted[bullet.id] = _coerce_relevance_score(base_score + 0.5)
        else:
            boosted[bullet.id] = _coerce_relevance_score(base_score)
    return boosted


def _tokenize_gap_terms(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in _GAP_TOKEN_PATTERN.findall(text.lower()):
        token = raw_token.strip("._-")
        if len(token) < 3 or token in _GAP_TOKEN_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _compute_jd_term_coverage(
    resume: ResumeIR,
) -> tuple[dict[str, int], set[str]]:
    """Tokenize the JD and resume content and return (job_term_counts, covered_terms).

    `job_term_counts` maps each unique JD token to its raw occurrence count
    (so `sum(values())` recovers the total token count). `covered_terms` is the
    set of tokens found anywhere in the resume's skills/experiences/bullets;
    callers intersect it with `job_term_counts` to compute coverage.
    """
    description_excerpt = ""
    role_hint = ""
    if resume.job_context is not None:
        description_excerpt = resume.job_context.description_excerpt.strip()
        role_hint = resume.job_context.role_hint.strip()

    job_terms = _tokenize_gap_terms(
        " ".join(part for part in [description_excerpt, role_hint] if part.strip())
    )
    job_term_counts: dict[str, int] = {}
    for term in job_terms:
        job_term_counts[term] = job_term_counts.get(term, 0) + 1

    covered_terms: set[str] = set()
    for skills in resume.skills_by_category.values():
        for skill in skills:
            covered_terms.update(_tokenize_gap_terms(skill))
    for experience in resume.experiences:
        covered_terms.update(_tokenize_gap_terms(experience.general_role_description))
        for skill in experience.related_skills:
            covered_terms.update(_tokenize_gap_terms(skill))
        for bullet in experience.bullets:
            covered_terms.update(_tokenize_gap_terms(bullet.text))
            for skill in bullet.skills:
                covered_terms.update(_tokenize_gap_terms(skill))
    return job_term_counts, covered_terms


def write_gap_summary(resume: ResumeIR, output_path: Path) -> None:
    """Write missing high-value JD terms not yet covered by selected skills/bullets."""
    job_term_counts, covered_terms = _compute_jd_term_coverage(resume)

    missing_terms = [
        {"term": term, "count": count}
        for term, count in sorted(
            job_term_counts.items(), key=lambda item: (-item[1], item[0])
        )
        if term not in covered_terms
    ]

    payload = {
        "target_role": resume.target_role,
        "target_company": resume.target_company,
        "job_term_count": sum(job_term_counts.values()),
        "unique_job_terms": len(job_term_counts),
        "covered_term_count": sum(
            1 for term in job_term_counts if term in covered_terms
        ),
        "missing_terms": missing_terms,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


DECISION_REPORT_SCHEMA_VERSION = 1


def write_decision_report(
    resume: ResumeIR,
    baseline_resume: ResumeIR,
    *,
    removal_reasons: dict[str, str],
    output_path: Path,
    processing_mode: str = "processed",
) -> None:
    """Emit a JSON explainability artifact describing this build's decisions.

    Compares the assembled-but-pre-pipeline `baseline_resume` against the final
    `resume` to derive selected/rejected bullet sets, skill-category transitions,
    and JD coverage. `removal_reasons` is populated by `trim_by_rules` and maps
    bullet ids to their precise rejection reason ("duplicate", "action_word_cap",
    "line_budget"); ids absent from this map fall back to the generic
    "trimmed" label.
    """
    final_bullet_ids: set[str] = {
        bullet.id for experience in resume.experiences for bullet in experience.bullets
    }

    selected: list[dict[str, Any]] = []
    for experience in resume.experiences:
        for position, bullet in enumerate(experience.bullets):
            metadata = resume.enrichment_by_bullet_id.get(bullet.id, {})
            confidence = 0.0
            tags: list[str] = []
            if isinstance(metadata, dict):
                confidence = _coerce_relevance_score(metadata.get("confidence"))
                raw_tags = metadata.get("tags", [])
                if isinstance(raw_tags, list):
                    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]
            selected.append(
                {
                    "bullet_id": bullet.id,
                    "experience_id": experience.id,
                    "position": position,
                    "text": bullet.text,
                    "skills": list(bullet.skills),
                    "confidence": confidence,
                    "tags": tags,
                    "has_measurable_outcome": _has_measurable_outcome(bullet.text),
                }
            )

    rejected: list[dict[str, Any]] = []
    for experience in baseline_resume.experiences:
        for bullet in experience.bullets:
            if bullet.id in final_bullet_ids:
                continue
            rejected.append(
                {
                    "bullet_id": bullet.id,
                    "experience_id": experience.id,
                    "text": bullet.text,
                    "reason": removal_reasons.get(bullet.id, "trimmed"),
                }
            )

    skills_section = _build_skill_decisions(
        baseline=baseline_resume.skills_by_category,
        final=resume.skills_by_category,
    )
    coverage_section = _build_jd_coverage(resume)

    payload: dict[str, Any] = {
        "schema_version": DECISION_REPORT_SCHEMA_VERSION,
        "target_role": resume.target_role,
        "target_company": resume.target_company,
        "processing_mode": processing_mode,
        "bullets": {
            "selected": selected,
            "rejected": rejected,
        },
        "skills": skills_section,
        "jd_coverage": coverage_section,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _build_skill_decisions(
    *,
    baseline: dict[str, list[str]],
    final: dict[str, list[str]],
) -> dict[str, Any]:
    """Diff baseline vs final skills_by_category to surface category transitions."""
    baseline_skill_to_cat: dict[str, str] = {}
    for category, skills in baseline.items():
        for skill in skills:
            baseline_skill_to_cat.setdefault(skill, category)
    final_skill_to_cat: dict[str, str] = {}
    for category, skills in final.items():
        for skill in skills:
            final_skill_to_cat.setdefault(skill, category)

    baseline_skill_set = set(baseline_skill_to_cat)
    final_skill_set = set(final_skill_to_cat)
    inferred_skills = sorted(final_skill_set - baseline_skill_set)
    dropped_skills = sorted(baseline_skill_set - final_skill_set)

    skill_moves: list[dict[str, str]] = []
    for skill in sorted(baseline_skill_set & final_skill_set):
        source_category = baseline_skill_to_cat[skill]
        destination_category = final_skill_to_cat[skill]
        if source_category != destination_category:
            skill_moves.append(
                {
                    "skill": skill,
                    "from": source_category,
                    "to": destination_category,
                }
            )

    category_merges: list[dict[str, Any]] = []
    dropped_categories = sorted(set(baseline) - set(final))
    for category in dropped_categories:
        moved_to_counts: dict[str, list[str]] = {}
        for skill in baseline[category]:
            destination = final_skill_to_cat.get(skill)
            if destination and destination != category:
                moved_to_counts.setdefault(destination, []).append(skill)
        if not moved_to_counts:
            continue
        # Pick the destination that received the most skills; ties broken
        # alphabetically so output is deterministic.
        target_category = sorted(
            moved_to_counts.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )[0][0]
        category_merges.append(
            {
                "from": category,
                "into": target_category,
                "skills_moved": sorted(moved_to_counts[target_category]),
            }
        )

    return {
        "categories_before": {
            category: list(skills) for category, skills in baseline.items()
        },
        "categories_after": {
            category: list(skills) for category, skills in final.items()
        },
        "category_merges": category_merges,
        "category_renames": [],
        "categories_dropped": dropped_categories,
        "skill_moves": skill_moves,
        "skills_dropped": dropped_skills,
        "inferred_skills": inferred_skills,
    }


def _build_jd_coverage(resume: ResumeIR) -> dict[str, Any]:
    """Compute JD coverage breakdown for the decision report."""
    job_term_counts, covered_terms = _compute_jd_term_coverage(resume)

    covered_in_jd = sorted(term for term in job_term_counts if term in covered_terms)
    missing_terms = [
        {"term": term, "count": count}
        for term, count in sorted(
            job_term_counts.items(), key=lambda item: (-item[1], item[0])
        )
        if term not in covered_terms
    ]
    return {
        "job_term_count": sum(job_term_counts.values()),
        "unique_job_term_count": len(job_term_counts),
        "covered_term_count": len(covered_in_jd),
        "missing_term_count": len(missing_terms),
        "covered_terms": covered_in_jd,
        "missing_terms": missing_terms,
    }


def _coerce_relevance_score(raw: object) -> float:
    try:
        numeric = float(str(raw))
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):
        return 0.0
    if numeric < 0.0:
        return 0.0
    if numeric > 1.0:
        return 1.0
    return numeric


def enrich_data(resume: ResumeIR) -> ResumeIR:
    """Attach role-alignment metadata to bullets without changing display content.

    Purpose:
        Annotate selected bullets with non-displayed metadata (confidence/tags).

    Allowed:
        - Add metadata keyed by bullet id.

    Not allowed:
        - Rewrite bullet text.
        - Select/reorder bullets.
    """
    if resume.job_context is None:
        return resume
    role_signal = resume.target_role.strip() or resume.job_context.role_hint.strip()
    if not resume.job_context.description_excerpt.strip() and not role_signal:
        return resume
    if not _llm_stage_enabled():
        return resume

    try:
        client = LLMClient.from_env()
        merged = dict(resume.enrichment_by_bullet_id)
        for experience in resume.experiences:
            merged.update(
                _enrich_experience_bullets(
                    client=client,
                    resume=resume,
                    experience=experience,
                )
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("enrich_data fallback to baseline: %s", exc)
        return resume

    return ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=merged,
        cross_org_architectural_leadership=resume.cross_org_architectural_leadership,
        selected_achievements=resume.selected_achievements,
        independent_projects=resume.independent_projects,
        independent_projects_visibility=resume.independent_projects_visibility,
    )


def _llm_stage_enabled() -> bool:
    llm_enabled = os.getenv(LLM_ENABLED_ENV, "0").strip() == "1"
    fixture_enabled = os.getenv(LLM_FIXTURE_ENV, "0").strip() == "1"
    return llm_enabled or fixture_enabled


def _resolve_top_skills_cap(args: argparse.Namespace) -> int:
    """Pick the top-N skills cap for the current run.

    Priority: explicit CLI override (``--top-skills-cap``) > LLM-enabled
    default > deterministic default. Tunable so the cap can be re-evaluated
    against real JD content; see DESIGN.md "Top-N skill cap".
    """
    override = getattr(args, "top_skills_cap", None)
    if override is not None:
        return int(override)
    if _llm_stage_enabled():
        return int(TOP_N_SKILLS_LLM_ENABLED)
    return int(TOP_N_SKILLS)


def _jd_context_required(args: argparse.Namespace) -> bool:
    """Return True when the JD-context gate should hard-fail empty ingest.

    Either the CLI flag or the env var independently enables the gate;
    the OR-semantics let CI / shell turn gating on (via env=1) without
    each call site needing the flag, and let an interactive caller turn
    gating on (via the flag) without exporting an env var. Truthy
    env = literal "1".

    Note: there is no override-down semantic. Setting the env var to
    "0" while passing --require-jd-context still gates, because the
    explicit flag wins as the per-call signal. To disable gating, pass
    no flag AND leave the env var unset / non-"1".
    """
    flag = bool(getattr(args, "require_jd_context", False))
    env = os.getenv(REQUIRE_JD_CONTEXT_ENV, "0").strip() == "1"
    return flag or env


def _extract_company_via_llm(job_context: JobContext) -> str:
    """Ask the LLM to extract the hiring company name from a JD when the
    deterministic ingest layer found nothing. Returns an empty string on any
    failure so the caller can fall back to the default 'company' slug.
    """
    text_parts: list[str] = []
    if job_context.page_title.strip():
        text_parts.append(f"Page title: {job_context.page_title.strip()}")
    if job_context.description_excerpt.strip():
        text_parts.append(f"Description: {job_context.description_excerpt.strip()}")
    if not text_parts:
        return ""
    payload_text = "\n\n".join(text_parts)
    try:
        client = LLMClient.from_env()
        response = client.complete_json(
            namespace="extract_company_name",
            system_prompt=(
                "You extract the hiring company name from job-description "
                'text. Reply with JSON only: {"company": "<name>"}. If '
                'no company is identifiable, reply with {"company": ""}.'
            ),
            user_payload={"text": payload_text},
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("LLM company extraction skipped: %s", exc)
        return ""
    company = response.get("company", "")
    if not isinstance(company, str):
        return ""
    return company.strip()


def _enrich_experience_bullets(
    *,
    client: LLMClient,
    resume: ResumeIR,
    experience: Experience,
) -> dict[str, dict[str, object]]:
    if resume.job_context is None:
        return {}

    response_payload = client.complete_json(
        namespace="enrich_data",
        system_prompt=(
            "You are annotating resume bullets with role-relevance metadata. "
            "Return JSON only with keys: bullets."
        ),
        user_payload={
            "target_role": resume.target_role.strip() or resume.job_context.role_hint,
            "target_company": (
                resume.target_company.strip() or resume.job_context.company_name
            ),
            "job_description_excerpt": resume.job_context.description_excerpt,
            "experience": {
                "id": experience.id,
                "job_title": experience.job_title,
                "company": experience.company,
            },
            "bullets": [
                {"id": bullet.id, "text": bullet.text, "skills": list(bullet.skills)}
                for bullet in experience.bullets
            ],
            "response_schema": {
                "bullets": [
                    {
                        "id": "<bullet-id>",
                        "confidence": "<float between 0.0 and 1.0>",
                        "tags": ["<short-tag>"],
                    }
                ]
            },
        },
    )

    raw_bullets = response_payload.get("bullets", [])
    if not isinstance(raw_bullets, list):
        return {}

    known_ids = {bullet.id for bullet in experience.bullets}
    parsed: dict[str, dict[str, object]] = {}
    for item in raw_bullets:
        if not isinstance(item, dict):
            continue
        bullet_id = str(item.get("id", "")).strip()
        if not bullet_id or bullet_id not in known_ids:
            continue

        raw_tags = item.get("tags", [])
        tags = []
        if isinstance(raw_tags, list):
            tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()]

        parsed[bullet_id] = {
            "confidence": _coerce_relevance_score(item.get("confidence")),
            "tags": tags,
        }
    return parsed


def trim_by_rules(
    resume: ResumeIR,
    *,
    removal_reasons: dict[str, str] | None = None,
) -> ResumeIR:
    """Apply deterministic layout and diversity trimming without rewriting text.

    Purpose:
        Enforce final presentation rules such as deduplication, action-word diversity,
        and an overall bullet budget.

    Allowed:
        - Remove duplicate or low-priority bullets.
        - Keep original bullet text unchanged.

    Not allowed:
        - Rewrite bullet text.
        - Reorder experiences.

    Future note:
        This stage does not currently perform layout-aware shortening. If page-fit
        constraints require small wording reductions, that should happen in a later
        overflow/layout stage after actual render measurement.
    """
    max_bullet_lines = _compute_bullet_line_budget(resume)
    trimmed_experiences = _apply_rule_based_trimming(
        experiences=resume.experiences,
        enrichment_by_bullet_id=resume.enrichment_by_bullet_id,
        max_bullet_lines=max_bullet_lines,
        removal_reasons=removal_reasons,
    )
    if trimmed_experiences == resume.experiences:
        return resume

    kept_bullet_ids = {
        bullet.id for experience in trimmed_experiences for bullet in experience.bullets
    }
    filtered_enrichment = {
        bullet_id: metadata
        for bullet_id, metadata in resume.enrichment_by_bullet_id.items()
        if bullet_id in kept_bullet_ids
    }

    return ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=trimmed_experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=filtered_enrichment,
        cross_org_architectural_leadership=resume.cross_org_architectural_leadership,
        selected_achievements=resume.selected_achievements,
        independent_projects=resume.independent_projects,
        independent_projects_visibility=resume.independent_projects_visibility,
    )


def summarize_for_role(resume: ResumeIR) -> ResumeIR:
    """Generate deterministic 1-2 line per-role summaries from selected bullets."""
    updated_experiences: list[Experience] = []
    changed = False
    for experience in resume.experiences:
        generated_summary = _generate_role_summary(resume, experience)
        if (
            generated_summary
            and generated_summary != experience.general_role_description
        ):
            updated_experiences.append(
                dc_replace(experience, general_role_description=generated_summary)
            )
            changed = True
        else:
            updated_experiences.append(experience)

    if not changed:
        return resume

    return dc_replace(resume, experiences=tuple(updated_experiences))


def summarize_profile_for_role(
    resume: ResumeIR,
    *,
    fit_assessment: FitAssessment | None = None,
) -> ResumeIR:
    """Generate a concise top-of-page summary from processed resume content.

    When LLM tailoring is enabled and the JD context has substantive
    content, prefer an LLM-tailored summary that conditions on the JD,
    target role, and company. On any LLM failure (disabled, fixture
    miss, malformed response, output outside word-budget bounds) fall
    back to the deterministic generator so behavior degrades gracefully.

    When ``fit_assessment`` is supplied, the LLM-tailored prompt is
    augmented to weave a fit-narrative clause into the summary within the
    same word/line budget (#272). The fit-narrative augmentation only
    applies to the LLM path; the deterministic fallback ignores it.
    """
    generated_summary = ""
    if _llm_stage_enabled() and _has_substantive_jd_context(resume):
        generated_summary = _generate_jd_tailored_summary_via_llm(
            resume, fit_assessment=fit_assessment
        )
    if not generated_summary:
        generated_summary = _generate_profile_summary(resume)
    if not generated_summary or generated_summary == resume.profile.summary:
        return resume

    updated_profile = dc_replace(resume.profile, summary=generated_summary)
    return dc_replace(resume, profile=updated_profile)


# Sentinel for "fit_assessment not provided" so callers can pass an explicit
# None (meaning the LLM call already returned None) without colliding with
# the back-compat default that triggers internal computation.
_FIT_ASSESSMENT_NOT_PROVIDED: object = object()


def _fit_assessment_will_be_consumed(args: argparse.Namespace) -> bool:
    """Return True when at least one downstream stage will read fit_assessment.

    Used by ``run_pipeline`` to skip the LLM round-trip entirely when no
    consumer can use the result (PR #278 review). Consumers:

    - ``_resolve_fit_narrative`` reads it whenever fit-narrative mode is
      not ``off`` and ``--cover-letter`` isn't suppressing auto-mode.
    - ``apply_experience_compression`` reads ``per_experience_scores`` only
      in ``auto`` mode (``top-N`` uses recency ordering, ``all`` is a no-op).

    The check is intentionally conservative: when in doubt we still compute
    so other LLM-stage gates can short-circuit cheaply.
    """
    fit_mode = str(getattr(args, "fit_narrative", "auto") or "auto").strip().lower()
    if fit_mode not in _FIT_NARRATIVE_MODES:
        fit_mode = "auto"
    cover_letter_enabled = bool(getattr(args, "cover_letter", False))
    narrative_will_consume = fit_mode == "on" or (
        fit_mode == "auto" and not cover_letter_enabled
    )

    exp_mode = (
        str(
            getattr(args, "experience_mode", _EXPERIENCE_MODE_AUTO)
            or _EXPERIENCE_MODE_AUTO
        )
        .strip()
        .lower()
    )
    # auto-mode is the only experience-mode that reads per_experience_scores;
    # top-N orders by existing recency and all is a no-op.
    compression_will_consume = exp_mode == _EXPERIENCE_MODE_AUTO

    return narrative_will_consume or compression_will_consume


def _resolve_fit_narrative(
    args: argparse.Namespace,
    resume: ResumeIR,
    *,
    fit_assessment: FitAssessment | None | object = _FIT_ASSESSMENT_NOT_PROVIDED,
) -> FitAssessment | None:
    """Decide whether the fit-narrative summary augmentation should fire (#272).

    Callers should pass the **pre-pipeline baseline resume** (not the trimmed
    view) so the LLM scores against the candidate's full canonical bullet set;
    #271's per-experience compression decision will also rely on the untrimmed
    signal once it lands.

    Returns the cached :class:`FitAssessment` payload when firing (so the
    caller can pass the rationale into the prompt and log it). Returns
    ``None`` when skipping for any reason: explicit ``--fit-narrative off``,
    auto-mode deferral (``--cover-letter`` on, LLM stages disabled, no
    substantive JD context), assessment failure, or auto-mode score above
    the ``_FIT_NARRATIVE_GATE_SCORE`` gate.
    """
    # Defensive normalization for programmatic callers that may build an
    # argparse.Namespace by hand and pass un-validated values; the CLI path
    # already runs the same canonicalization through _parse_fit_narrative_mode.
    raw_mode = getattr(args, "fit_narrative", "auto")
    mode = str(raw_mode or "auto").strip().lower()
    if mode not in _FIT_NARRATIVE_MODES:
        logger.info("fit_narrative coerced unexpected mode %r to 'auto'", raw_mode)
        mode = "auto"
    if mode == "off":
        logger.info("fit_narrative skipped: --fit-narrative off")
        return None
    cover_letter_enabled = bool(getattr(args, "cover_letter", False))
    if mode == "auto" and cover_letter_enabled:
        logger.info("fit_narrative skipped: --cover-letter enabled (auto-mode)")
        return None
    if not _llm_stage_enabled():
        logger.info("fit_narrative skipped: LLM stages disabled")
        return None
    if not _has_substantive_jd_context(resume):
        logger.info("fit_narrative skipped: JD context below threshold")
        return None
    # Accept a precomputed assessment so run_pipeline can compute it once
    # and feed both this resolver and apply_experience_compression without
    # paying for two LLMClient lookups (PR #278 review). Fall back to
    # computing internally for callers that don't supply one (back-compat).
    if fit_assessment is _FIT_ASSESSMENT_NOT_PROVIDED:
        assessment = compute_fit_assessment(resume)
    else:
        assessment = fit_assessment  # type: ignore[assignment]
    if assessment is None:
        logger.info("fit_narrative skipped: fit_assessment returned None")
        return None
    if mode == "auto" and assessment.overall_fit_score >= _FIT_NARRATIVE_GATE_SCORE:
        logger.info(
            "fit_narrative skipped: overall_fit_score=%.1f >= gate %d (rationale: %s)",
            assessment.overall_fit_score,
            _FIT_NARRATIVE_GATE_SCORE,
            assessment.overall_rationale or "<empty>",
        )
        return None
    logger.info(
        "fit_narrative firing (mode=%s, overall_fit_score=%.1f): %s",
        mode,
        assessment.overall_fit_score,
        assessment.overall_rationale or "<empty>",
    )
    return assessment


_COMPRESSION_PCT_CAP = 0.5  # ≥50% in-window experiences cannot all compress


def _force_all_full(resume: ResumeIR) -> ResumeIR:
    """Reset every experience to ``compression="full"``.

    Used by ``all`` and the no-context fallback so a stale ``"compressed"``
    marker from an earlier pass doesn't survive into the rendered output.
    Returns the input unchanged when nothing needs flipping.
    """
    if all(exp.compression == "full" for exp in resume.experiences):
        return resume
    return dc_replace(
        resume,
        experiences=tuple(
            dc_replace(exp, compression="full") if exp.compression != "full" else exp
            for exp in resume.experiences
        ),
    )


def apply_experience_compression(
    args: argparse.Namespace,
    resume: ResumeIR,
    *,
    fit_assessment: FitAssessment | None,
) -> ResumeIR:
    """Mark experiences as ``"compressed"`` per ``--experience-mode`` (#271).

    Compression is purely a render-level switch: experiences are *never*
    dropped (chronology is preserved). Only ``experience.compression`` is
    flipped from ``"full"`` to ``"compressed"``; the renderer reads this to
    emit `title — date_range` plus the single highest-relevance bullet.

    Modes:

    - ``all`` — no-op (every experience renders in full).
    - ``top-N`` — top N by the existing ``_prepare_display_experiences``
      sort key (recency × bullet-confidence) render full; the rest are
      marked compressed, subject to the 50% cap.
    - ``auto`` — layout-driven. If the current bullet line count exceeds
      the budget computed by ``_compute_bullet_line_budget``, compress
      lowest-``fit_score`` experience (by ``fit_assessment``) first, repeat
      until under budget or the 50% cap is hit. When ``fit_assessment`` is
      None, falls back to ``top-N`` ordering with N = remaining-uncompressed
      cap.

    No-context fallback: when ``job_context`` is missing or below the
    substantive-content threshold, force ``all`` regardless of flag.
    """
    raw_mode = getattr(args, "experience_mode", _EXPERIENCE_MODE_AUTO)
    mode = str(raw_mode or _EXPERIENCE_MODE_AUTO).strip().lower()
    # Defensive fallback: invalid programmatic values become 'auto'.
    if mode not in {_EXPERIENCE_MODE_AUTO, _EXPERIENCE_MODE_ALL} and (
        _experience_mode_top_n(mode) is None
    ):
        logger.info(
            "apply_experience_compression coerced unexpected mode %r to 'auto'",
            raw_mode,
        )
        mode = _EXPERIENCE_MODE_AUTO

    # Always start from a clean "full" baseline so stale compression markers
    # from a prior pass / programmatic caller don't leak through. Without
    # this reset, an auto/top-N run that decides nothing should compress
    # would silently keep pre-existing "compressed" markers (PR #278 review).
    resume = _force_all_full(resume)

    if not _has_substantive_jd_context(resume):
        # No JD signal -> safe default is full mode regardless of flag.
        logger.info(
            "apply_experience_compression: no-context fallback forces 'all' mode"
        )
        return resume

    if mode == _EXPERIENCE_MODE_ALL:
        # all-mode contract is "every experience full" — reset already happened.
        return resume

    in_window = list(resume.experiences)
    if not in_window:
        return resume

    # 50% cap: integer floor — at most floor(N/2) of N experiences compressed.
    max_compressible = int(len(in_window) * _COMPRESSION_PCT_CAP)
    if max_compressible == 0:
        return resume

    top_n = _experience_mode_top_n(mode)
    score_by_id: dict[str, float] = {}
    if fit_assessment is not None:
        score_by_id = {
            entry.experience_id: entry.fit_score
            for entry in fit_assessment.per_experience_scores
        }

    # Sort experiences by *worst-first* compression candidate ordering.
    # - top-N: rank by existing _prepare_display_experiences key (descending);
    #   experiences beyond rank N go first.
    # - auto with fit_assessment: lowest fit_score first.
    # - auto without fit_assessment: fall back to "lowest-ranked first" using
    #   reverse of input order. Since _prepare_display_experiences already
    #   orders by relevance descending, reversing gives lowest-relevance
    #   first — the correct worst-first direction. (PR #278 review.)
    #
    # Bullet-less experiences can't satisfy the compressed-mode contract
    # ("title — date_range plus the single highest-relevance bullet"). Their
    # general_role_description in full mode IS the only signal they carry,
    # so compressing them to title+dates would drop that signal entirely.
    # Exclude them from the candidate set; they always stay full. The 50%
    # cap remains based on len(in_window) since the cap is about visible
    # rendered roles, not just bullet-bearing ones (PR #278 review).
    indexed = [(idx, exp) for idx, exp in enumerate(in_window) if exp.bullets]
    if top_n is not None:
        # top-N's boundary is computed against the full visible-roles list
        # (in_window), then filtered to bullet-bearing candidates. A bullet-
        # less role inside the first N positions still takes one of those
        # slots — matches the spec's "top N visible roles" reading. Without
        # this, slicing the bullet-bearing-filtered list directly skewed the
        # boundary by 1 per bullet-less role in the prefix (issue #299).
        # _prepare_display_experiences orders descending by relevance, so the
        # bottom of the beyond-N slice is the lowest-ranked. Reverse so when
        # the 50% cap applies we keep the *worst* of the demoted group
        # compressed (PR #278 review).
        beyond_n = list(enumerate(in_window))[top_n:]
        candidates = list(
            reversed([(idx, exp) for idx, exp in beyond_n if exp.bullets])
        )
    elif fit_assessment is None:
        # Deterministic fallback: lowest-ranked first.
        candidates = list(reversed(indexed))
    else:
        # auto with assessment: lowest fit_score first. Experiences missing
        # from per_experience_scores get a neutral midpoint so they sort
        # alongside scored experiences without crashing.
        def _auto_key(item: tuple[int, Experience]) -> tuple[float, int]:
            idx, exp = item
            score = score_by_id.get(exp.id, 50.0)
            return (score, idx)

        candidates = sorted(indexed, key=_auto_key)

    if mode == _EXPERIENCE_MODE_AUTO:
        # Layout overflow check: compress only as needed.
        budget = _compute_bullet_line_budget(resume)
        current = _estimate_total_bullet_lines([list(exp.bullets) for exp in in_window])
        if current <= budget:
            return resume
        compressed_ids: set[str] = set()
        for _idx, exp in candidates:
            if len(compressed_ids) >= max_compressible:
                break
            compressed_ids.add(exp.id)
            # Build a simulated resume that reflects the proposed
            # compression: compressed experiences emit a single bullet AND
            # omit the role-summary line, which frees non-bullet space.
            # Rebuilding the budget from this simulated resume credits that
            # freed space back into the bullet budget so we don't compress
            # more experiences than necessary (PR #278 review).
            simulated_experiences = tuple(
                dc_replace(
                    cand_exp,
                    general_role_description="",
                    bullets=cand_exp.bullets[:1],
                )
                if cand_exp.id in compressed_ids
                else cand_exp
                for cand_exp in in_window
            )
            simulated_resume = dc_replace(resume, experiences=simulated_experiences)
            simulated_budget = _compute_bullet_line_budget(simulated_resume)
            simulated_lines = _estimate_total_bullet_lines(
                [list(exp.bullets) for exp in simulated_experiences]
            )
            if simulated_lines <= simulated_budget:
                break
    else:
        # top-N: compress everything beyond rank N up to the 50% cap.
        compressed_ids = {exp.id for _, exp in candidates[:max_compressible]}

    if not compressed_ids:
        return resume

    new_experiences = tuple(
        dc_replace(exp, compression="compressed") if exp.id in compressed_ids else exp
        for exp in in_window
    )
    return dc_replace(resume, experiences=new_experiences)


def _has_substantive_jd_context(resume: ResumeIR) -> bool:
    """True when the JD description has enough content for a tailored summary.

    Reuses the same _MIN_JD_DESCRIPTION_CHARS threshold used by the
    --require-jd-context gate so the two never disagree on what
    "substantive" means.
    """
    if resume.job_context is None:
        return False
    return (
        len(resume.job_context.description_excerpt or "") >= _MIN_JD_DESCRIPTION_CHARS
    )


@dataclass(frozen=True)
class FitExperienceScore:
    experience_id: str
    fit_score: float
    rationale: str


@dataclass(frozen=True)
class FitAssessment:
    """Shared LLM-judged fit assessment, consumed by #272 and #271.

    Fields use a 0-100 scale where higher means stronger fit. Emitted as a
    single LLM round-trip so #272's narrative gate and #271's per-experience
    compression decision read from one cached payload.
    """

    overall_fit_score: float
    overall_rationale: str
    per_experience_scores: tuple[FitExperienceScore, ...]


def _coerce_fit_score(raw: object) -> float | None:
    """Validate a 0-100 fit score; return None for unusable inputs.

    Booleans are explicitly rejected because ``float(True) == 1.0`` would
    silently accept a malformed LLM response (e.g. ``true``) as a real
    score and skew the gate. Non-finite floats (NaN, inf) are rejected
    via ``math.isfinite``.
    """
    if isinstance(raw, bool):
        return None
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if value < 0.0 or value > 100.0:
        return None
    return value


def compute_fit_assessment(resume: ResumeIR) -> FitAssessment | None:
    """Run the shared fit_assessment LLM call (#272).

    Returns ``None`` on any failure so callers fall back gracefully:

    - LLM stages disabled (`RESUME_BUILDER_LLM_ENABLED` unset and not in
      fixture mode).
    - JD context missing or below the substantive-content threshold.
    - LLM call raises (network, JSON-decode, etc.).
    - Response missing required fields, has wrong shape, or carries a
      score outside the 0-100 range.

    The response is cached by ``LLMClient`` under ``namespace=fit_assessment``
    so a successful call costs one round-trip per (JD × resume) regardless
    of how many consumers (#272 narrative gate, #271 compression) read it.
    """
    if not _llm_stage_enabled():
        return None
    if not _has_substantive_jd_context(resume):
        return None
    job_context = resume.job_context
    if job_context is None:
        return None

    experience_signals: list[dict[str, object]] = []
    known_experience_ids: set[str] = set()
    for experience in resume.experiences:
        experience_id = (experience.id or "").strip()
        if not experience_id:
            continue
        known_experience_ids.add(experience_id)
        experience_signals.append(
            {
                "experience_id": experience_id,
                "job_title": (experience.job_title or "").strip(),
                "company": (experience.company or "").strip(),
                "general_role_description": (
                    experience.general_role_description or ""
                ).strip(),
                "bullets": [
                    (bullet.text or "").strip() for bullet in experience.bullets
                ],
            }
        )

    user_payload: dict[str, object] = {
        "candidate_summary": (resume.profile.summary or "").strip(),
        "target_role": (resume.target_role or "").strip(),
        "target_company": (resume.target_company or "").strip(),
        "jd_excerpt": (job_context.description_excerpt or "").strip(),
        "experiences": experience_signals,
    }
    # Mirror the jd_tailored_summary cache-key handling: only include
    # candidate_current_level when non-empty so profiles that don't set it
    # have an unchanged cache key.
    current_level = (resume.profile.current_level or "").strip()
    if current_level:
        user_payload["candidate_current_level"] = current_level

    try:
        client = LLMClient.from_env()
        response = client.complete_json(
            namespace="fit_assessment",
            system_prompt=(
                "You assess how well a candidate's experience fits a job "
                "description. Score fit on a 0-100 scale where 100 means "
                "strongest possible fit and 0 means no relevant signal. "
                "Consider experience depth, domain match, and seniority "
                "signals together; do NOT weight job titles alone. Use "
                "the input's candidate_current_level as additional "
                "seniority context when it is non-empty; otherwise judge "
                "fit purely from experience content. Reply with JSON only "
                "matching this schema: "
                '{"overall_fit_score": <0-100 number>, '
                '"overall_rationale": "<short string>", '
                '"per_experience_scores": [{"experience_id": "<id from input>", '
                '"fit_score": <0-100 number>, "rationale": "<short string>"}]}. '
                "Include one entry per input experience using the exact "
                "experience_id values from the input."
            ),
            user_payload=user_payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("fit_assessment skipped: %s", exc)
        return None

    overall_score = _coerce_fit_score(response.get("overall_fit_score"))
    if overall_score is None:
        logger.info("fit_assessment rejected: invalid overall_fit_score")
        return None

    overall_rationale = response.get("overall_rationale", "")
    if not isinstance(overall_rationale, str):
        overall_rationale = ""

    raw_per_experience = response.get("per_experience_scores", [])
    if not isinstance(raw_per_experience, list):
        logger.info("fit_assessment rejected: per_experience_scores not a list")
        return None

    per_experience: list[FitExperienceScore] = []
    seen_ids: set[str] = set()
    for item in raw_per_experience:
        if not isinstance(item, dict):
            continue
        experience_id = item.get("experience_id", "")
        if not isinstance(experience_id, str):
            continue
        experience_id = experience_id.strip()
        if not experience_id or experience_id in seen_ids:
            continue
        if experience_id not in known_experience_ids:
            logger.info(
                "fit_assessment dropping unknown experience_id=%s", experience_id
            )
            continue
        score = _coerce_fit_score(item.get("fit_score"))
        if score is None:
            continue
        rationale = item.get("rationale", "")
        if not isinstance(rationale, str):
            rationale = ""
        per_experience.append(
            FitExperienceScore(
                experience_id=experience_id,
                fit_score=score,
                rationale=rationale.strip(),
            )
        )
        seen_ids.add(experience_id)

    # Reject payloads that don't cover every known experience. The prompt
    # asks for "one entry per input experience" and #271 will use this
    # mapping to decide compression — caching a partial set would silently
    # miscompress. If the resume has no experiences (synthetic edge case),
    # the response just needs to lack per-experience entries to be valid.
    if known_experience_ids and seen_ids != known_experience_ids:
        missing = sorted(known_experience_ids - seen_ids)
        logger.info(
            "fit_assessment rejected: per_experience_scores missing entries "
            "for known experience_id(s): %s",
            ", ".join(missing),
        )
        return None

    return FitAssessment(
        overall_fit_score=overall_score,
        overall_rationale=overall_rationale.strip(),
        per_experience_scores=tuple(per_experience),
    )


def _generate_jd_tailored_summary_via_llm(
    resume: ResumeIR,
    *,
    fit_assessment: FitAssessment | None = None,
) -> str:
    """Ask the LLM for a JD-conditioned summary; validate bounds + layout.

    Returns an empty string on any failure so the caller falls back to
    the deterministic _generate_profile_summary path. Failure modes:

    - LLM-stage gating off (RESUME_BUILDER_LLM_ENABLED unset and not in
      fixture mode) — checked defensively so the function is safe to
      call from anywhere, not just summarize_profile_for_role.
    - No JobContext on the resume.
    - Raised exception during the LLM call (network, JSON-decode, etc.).
    - Malformed response (missing key, non-string value, empty/whitespace
      string).
    - Word count outside [_LLM_SUMMARY_MIN_WORDS, PROFILE_SUMMARY_MAX_WORDS]
      (currently [30, 112]). The lower bound is a sanity floor — much
      shorter than that suggests a fragmented or otherwise broken LLM
      response. The upper bound matches the deterministic generator's
      pre-fitting cap. The real layout guardrail is the wrap-line check
      below.
    - Wrap-line count above PROFILE_SUMMARY_MAX_LINES (6) when wrapped
      at PROFILE_SUMMARY_LINE_WIDTH (115) — the same 6-line PDF layout
      cap that _fit_profile_summary_layout enforces on the deterministic
      path.

    When ``fit_assessment`` is provided, the system prompt is augmented to
    weave a fit-narrative clause into the summary within the same word and
    line budget (#272). The wrap-line and word-count guardrails still apply
    — the augmentation does not bump the budget.
    """
    if not _llm_stage_enabled():
        return ""
    job_context = resume.job_context
    if job_context is None:
        return ""

    max_words = max(1, int(PROFILE_SUMMARY_MAX_WORDS))
    min_words = min(max_words, max(1, _LLM_SUMMARY_MIN_WORDS))

    top_skills = _collect_resume_skill_signals(resume)[:6]
    experience_signals: list[dict[str, str]] = []
    for experience in resume.experiences[:4]:
        experience_signals.append(
            {
                "role": (experience.job_title or "").strip(),
                "company": (experience.company or "").strip(),
                "summary": (experience.general_role_description or "").strip(),
            }
        )

    user_payload: dict[str, object] = {
        "candidate_name": resume.profile.name,
        "candidate_baseline_summary": (resume.profile.summary or "").strip(),
        "target_company": resume.target_company or "",
        "target_role": resume.target_role or "",
        "top_skills": top_skills,
        "recent_experiences": experience_signals,
        "jd_excerpt": (job_context.description_excerpt or "").strip(),
        "min_words": min_words,
        "max_words": max_words,
    }

    # Only include current_level when set, so profiles that don't supply it
    # have an unchanged cache key vs. pre-#272 (no spurious cache misses).
    current_level = (resume.profile.current_level or "").strip()
    if current_level:
        user_payload["candidate_current_level"] = current_level

    base_prompt = (
        "You write the opening summary paragraph of a resume "
        "tailored to a specific job description. Output exactly "
        "one paragraph between min_words and max_words words "
        "summarising how the candidate's actual experience and "
        "skills fit the target role at the target company. Use "
        "concrete details from recent_experiences and top_skills "
        "when relevant; if candidate_current_level is provided, "
        "frame the summary at that seniority. Do NOT invent "
        "achievements. Preserve acronym casing (SDET, QA, CI/CD, "
        "REST, SQL). Do NOT include the candidate's name, the "
        "company name, or the literal target role in the output. "
        'Reply with JSON only: {"summary": "<paragraph>"}.'
    )
    if fit_assessment is not None:
        user_payload["fit_narrative_rationale"] = fit_assessment.overall_rationale or ""
        user_payload["fit_narrative_overall_score"] = fit_assessment.overall_fit_score
        system_prompt = base_prompt + (
            " Additionally, weave a single short fit-narrative clause into "
            "the same paragraph guided by fit_narrative_rationale and "
            "fit_narrative_overall_score: address how the candidate's "
            "experience translates to the JD's domain and seniority. Frame "
            "the clause neutrally — only emphasise stretch/translation "
            "language if the rationale or score actually indicates a gap; "
            "otherwise lean into how the existing strengths map directly. "
            "Do not invent achievements, do not repeat the JD verbatim, "
            "stay within the same word budget, and keep the output as one "
            "paragraph."
        )
    else:
        system_prompt = base_prompt

    try:
        client = LLMClient.from_env()
        response = client.complete_json(
            namespace="jd_tailored_summary",
            system_prompt=system_prompt,
            user_payload=user_payload,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("LLM JD-tailored summary skipped: %s", exc)
        return ""

    candidate = response.get("summary", "")
    if not isinstance(candidate, str):
        return ""
    candidate = " ".join(candidate.split())
    if not candidate:
        return ""

    word_count = len(candidate.split())
    if word_count < min_words or word_count > max_words:
        logger.info(
            "LLM JD-tailored summary rejected: %d words outside [%d, %d]",
            word_count,
            min_words,
            max_words,
        )
        return ""

    # Normalize terminal punctuation BEFORE measuring wrap lines: if
    # we appended the period after the wrap check, the period would
    # add a char to the last word which might no longer fit on the
    # line at PROFILE_SUMMARY_LINE_WIDTH and push a borderline summary
    # from 6 → 7 lines. Strip trailing list separators first so an
    # LLM response ending with `,` or `:` doesn't produce `,.` / `:.`
    # once the period is appended.
    candidate = candidate.rstrip(" ,;:")
    if not candidate:
        return ""
    if not candidate.endswith((".", "!", "?")):
        candidate += "."

    # If the LLM summary doesn't fit the 6-line profile-summary slot,
    # trim it the same way the deterministic path does
    # (_fit_profile_summary_layout pops trailing words / drops incomplete
    # tail clauses while preserving sentence boundaries AND re-applying
    # terminal-period normalization on each retry). Issue #282: the
    # prior policy was to REJECT and fall back to deterministic, on the
    # theory that a trimmed LLM summary might silently drop key
    # tailoring clauses. In practice that meant a 1-line overflow lost
    # 100% of the LLM's tailoring (e.g. v4 llama::becu produced 7 lines
    # over a 6-line cap → full deterministic fallback). Trimming retains
    # most of the tailoring and is still better than a generic
    # deterministic boilerplate. The wrap uses PROFILE_SUMMARY_LINE_WIDTH
    # (115) — the same width constant the deterministic path uses, NOT
    # the default SUMMARY_LINE_WIDTH (72) that's calibrated for the
    # narrower experience-bullet layout.
    wrap_lines = _summary_wrap_lines(candidate, line_width=PROFILE_SUMMARY_LINE_WIDTH)
    if len(wrap_lines) > PROFILE_SUMMARY_MAX_LINES:
        original_words = len(candidate.split())
        trimmed = _fit_profile_summary_layout(candidate)
        trimmed_words = len(trimmed.split()) if trimmed else 0
        if trimmed_words < min_words:
            # Trimming chewed too much — the LLM was wildly over-budget,
            # not just a small overflow. Fall back to deterministic.
            logger.info(
                "LLM JD-tailored summary rejected: %d wrap lines exceeds %d, "
                "trimmed to %d words below floor %d",
                len(wrap_lines),
                PROFILE_SUMMARY_MAX_LINES,
                trimmed_words,
                min_words,
            )
            return ""
        # Log the *actual* post-trim wrap-line count, not the cap —
        # `_fit_profile_summary_layout` can return fewer than the cap
        # (e.g. dropping a long word can remove multiple wrapped lines)
        # so reporting the cap would be misleading.
        trimmed_line_count = len(
            _summary_wrap_lines(trimmed, line_width=PROFILE_SUMMARY_LINE_WIDTH)
        )
        logger.info(
            "LLM JD-tailored summary trimmed to fit layout: "
            "%d → %d wrap lines (cap %d), %d → %d words",
            len(wrap_lines),
            trimmed_line_count,
            PROFILE_SUMMARY_MAX_LINES,
            original_words,
            trimmed_words,
        )
        # `_fit_profile_summary_layout` returns a sentence-safe,
        # period-terminated string — no further normalization needed.
        candidate = trimmed

    return candidate


def _generate_profile_summary(resume: ResumeIR) -> str:
    """Generate a concise top-of-page summary from processed resume content.

    Uses the rendered/profile resume title for framing.
    target_role and job role hints are internal tailoring inputs and must not
    leak into visible summary text.
    Preserves acronym casing (e.g., SDET, QA, Python) in skill descriptions.
    """
    role_label = _summary_role_label_from_title(resume)
    role_label = role_label or "Engineer"
    skills = _collect_resume_skill_signals(resume)
    if len(skills) >= 3:
        focus_text = f"{skills[0]}, {skills[1]}, and {skills[2]}"
    elif len(skills) == 2:
        focus_text = f"{skills[0]} and {skills[1]}"
    elif skills:
        focus_text = skills[0]
    else:
        focus_text = "framework architecture, CI quality gates, and defect isolation"

    fragments = _build_profile_summary_fragments(
        resume, role_label=role_label, focus_text=focus_text
    )
    if not fragments:
        return ""
    candidate = fragments[0]
    words = candidate.split()
    max_words = max(1, int(PROFILE_SUMMARY_MAX_WORDS))
    min_words = min(max_words, max(1, math.ceil(max_words * PROFILE_SUMMARY_MIN_RATIO)))
    if len(words) < min_words:
        candidate = _expand_profile_summary_to_min_words(
            candidate, resume, min_words, fragments=fragments[1:]
        )
        words = candidate.split()
    if len(words) > max_words:
        truncated = _truncate_to_n_words(candidate, max_words).rstrip(" ,;:")
        # Avoid double punctuation when appending period
        if not truncated.endswith((".", "!", "?")):
            candidate = truncated + "."
        else:
            candidate = truncated
    fitted = _fit_profile_summary_layout(candidate)
    # Ensure final summary is at most max_words after all processing
    max_words = max(1, int(PROFILE_SUMMARY_MAX_WORDS))
    final = fitted or candidate
    final = _truncate_to_n_words(final, max_words)
    # Strip trailing punctuation before adding period to avoid sequences like "Video,."
    final = final.rstrip(" ,;:")
    # Add period if missing
    if final and not final.endswith((".", "!", "?")):
        final += "."
    return final


def _fit_profile_summary_layout(summary: str) -> str:
    """Trim summary tail until it fits the six-line profile-summary layout budget."""
    original_words = summary.strip().replace("\n", " ").split()
    words = list(original_words)
    while words:
        words = _trim_trailing_fragment_words(words)
        if not words:
            return ""
        candidate = " ".join(words).strip(" ,;:")
        if candidate and candidate[-1] not in ".!?":
            if len(words) < len(original_words):
                sentence_safe = _truncate_to_last_complete_sentence(candidate)
                if sentence_safe:
                    candidate = sentence_safe
                else:
                    candidate = f"{candidate}."
            else:
                candidate = f"{candidate}."
        lines = _summary_wrap_lines(candidate, line_width=PROFILE_SUMMARY_LINE_WIDTH)
        if len(lines) <= PROFILE_SUMMARY_MAX_LINES:
            return candidate
        words.pop()
    return ""


def _truncate_to_n_words(text: str, n: int) -> str:
    words = text.split()
    if not words:
        return ""
    if len(words) <= n:
        return text

    clipped = " ".join(words[:n]).strip()
    if clipped.endswith((".", "!", "?")):
        return clipped

    sentence_matches = list(re.finditer(r".+?[.!?](?:\s+|$)", clipped))
    if sentence_matches:
        sentence_safe = sentence_matches[-1].group(0).strip()
        if sentence_safe:
            return sentence_safe

    trimmed_words = _trim_trailing_fragment_words(clipped.split())
    return " ".join(trimmed_words).strip()


def _truncate_to_last_complete_sentence(text: str) -> str:
    matches = list(re.finditer(r".+?[.!?](?:\s+|$)", text.strip()))
    if not matches:
        return ""
    return text[: matches[-1].end()].strip()


def _build_profile_summary_fragments(
    resume: ResumeIR, *, role_label: str, focus_text: str
) -> list[str]:
    normalized_role_label = " ".join(role_label.split()).strip() or "Engineer"
    fragments = [
        _build_profile_scope_opening(resume, normalized_role_label),
        f"Core strengths include {focus_text}.",
    ]

    for exp_index, experience in enumerate(resume.experiences):
        summary = _shorten_sentence(experience.general_role_description, max_words=30)
        if summary:
            fragments.append(summary)
        if exp_index < 2 and experience.bullets:
            bullet_summary = _shorten_sentence(experience.bullets[0].text, max_words=18)
            if bullet_summary:
                fragments.append(bullet_summary)

    deduped: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        normalized = " ".join(fragment.split()).lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(fragment)
    return deduped


def _build_profile_scope_opening(resume: ResumeIR, role_label: str) -> str:
    """Build a scope-first opening sentence for the profile summary."""
    labels = _collect_profile_scope_labels(resume.experiences)
    if len(labels) >= 3:
        scope = f"{labels[0]}, {labels[1]}, and {labels[2]}"
    elif len(labels) == 2:
        scope = f"{labels[0]} and {labels[1]}"
    elif labels:
        scope = labels[0]
    else:
        scope = "multi-product"
    return (
        f"{role_label} delivering automation framework architecture across {scope} "
        "product teams."
    )


def _collect_profile_scope_labels(experiences: tuple[Experience, ...]) -> list[str]:
    """Extract deterministic scope labels from experience titles/descriptions."""
    token_to_label = {
        "video": "Video",
        "audio": "Audio",
        "headset": "Headset",
        "network": "Network",
    }
    discovered: set[str] = set()
    for experience in experiences:
        haystack = (
            f"{experience.job_title} {experience.general_role_description}".lower()
        )
        for token, label in token_to_label.items():
            if token in haystack:
                discovered.add(label)
    return [
        label
        for label in ("Video", "Audio", "Headset", "Network")
        if label in discovered
    ]


def _summary_role_label_from_title(resume: ResumeIR) -> str:
    """Extract a readable role label for fallback summary text."""
    title = derive_resume_title(resume).strip()
    if not title:
        return "Engineer"
    # Keep hyphenated role words intact (e.g., "Full-stack Engineer").
    primary_segment = re.split(r"\s*(?:/|,)\s*", title, maxsplit=1)[0].strip()
    return primary_segment or "Engineer"


def _expand_profile_summary_to_min_words(
    candidate: str,
    resume: ResumeIR,
    min_words: int,
    *,
    fragments: Sequence[str] = (),
) -> str:
    """Deterministically expand summaries until they satisfy the minimum word policy."""
    additions = list(fragments)

    existing_sentences = {
        " ".join(part.strip().split()).lower()
        for part in re.split(r"(?<=[.!?])\s+", candidate)
        if part.strip()
    }

    # Preserve deterministic order while removing duplicate sentences.
    deduped_additions: list[str] = []
    seen: set[str] = set()
    for addition in additions:
        normalized = " ".join(addition.split()).lower()
        if not normalized or normalized in seen or normalized in existing_sentences:
            continue
        seen.add(normalized)
        deduped_additions.append(addition)

    if not deduped_additions:
        skills = _collect_resume_skill_signals(resume)
        if len(skills) >= 2:
            deduped_additions.append(f"Focus includes {skills[0]} and {skills[1]}.")
        elif skills:
            deduped_additions.append(f"Focus includes {skills[0]}.")
        else:
            role_label = _summary_role_label_from_title(resume)
            deduped_additions.append(f"Focus includes {role_label} delivery.")

    updated = candidate.rstrip()
    words = updated.split()
    index = 0
    while len(words) < min_words and deduped_additions:
        addition = (
            deduped_additions[index % len(deduped_additions)].strip().rstrip(" ,;:")
        )
        if not addition:
            index += 1
            continue
        if not addition.endswith((".", "!", "?")):
            addition += "."
        updated = f"{updated} {addition}".strip()
        words = updated.split()
        index += 1
    return updated


def _collect_resume_skill_signals(resume: ResumeIR) -> list[str]:
    scores: dict[str, float] = {}
    bullet_hits: dict[str, int] = {}
    related_hits: dict[str, int] = {}
    curated_hits: dict[str, int] = {}
    max_confidence: dict[str, float] = {}
    display_candidates: dict[str, set[str]] = {}

    def add_skill(
        raw_skill: str,
        *,
        weight: float,
        source: str,
        confidence: float = 0.0,
    ) -> None:
        cleaned = raw_skill.strip()
        if not cleaned:
            return
        lowered = cleaned.lower()
        scores[lowered] = scores.get(lowered, 0.0) + weight
        display_candidates.setdefault(lowered, set()).add(cleaned)

        if source == "bullet":
            bullet_hits[lowered] = bullet_hits.get(lowered, 0) + 1
            max_confidence[lowered] = max(max_confidence.get(lowered, 0.0), confidence)
        elif source == "related":
            related_hits[lowered] = related_hits.get(lowered, 0) + 1
        elif source == "curated":
            curated_hits[lowered] = curated_hits.get(lowered, 0) + 1

    # Primary relevance signal: selected bullets and enrichment confidence.
    for experience in resume.experiences:
        for bullet in experience.bullets:
            confidence = _bullet_confidence(bullet, resume.enrichment_by_bullet_id)
            weight = 1.0 + confidence
            for skill in bullet.skills:
                add_skill(
                    skill,
                    weight=weight,
                    source="bullet",
                    confidence=confidence,
                )

        for skill in experience.related_skills:
            add_skill(skill, weight=0.25, source="related")

    # Secondary deterministic signal from curated skills matrix categories.
    for category in sorted(resume.skills_by_category):
        for skill in resume.skills_by_category[category]:
            add_skill(skill, weight=0.4, source="curated")

    ranked = sorted(
        scores,
        key=lambda key: (
            -scores[key],
            -bullet_hits.get(key, 0),
            -max_confidence.get(key, 0.0),
            -related_hits.get(key, 0),
            -curated_hits.get(key, 0),
            key,
        ),
    )
    return [
        sorted(display_candidates[key], key=lambda value: (value.lower(), value))[0]
        for key in ranked[:3]
    ]


def _generate_role_summary(resume: ResumeIR, experience: Experience) -> str:
    role_seed = _summary_primary_clause(experience.general_role_description)
    role_sentence = _shorten_sentence(role_seed, max_words=24)
    if not role_sentence:
        role_sentence = _shorten_sentence(
            f"Delivered {experience.job_title} outcomes across {experience.company}.",
            max_words=24,
        )

    role_only = _fit_summary_layout(role_sentence, allow_single_word_wrap=True)
    if role_only:
        return role_only

    if experience.bullets:
        bullet_seed = _summary_primary_clause(experience.bullets[0].text)
        bullet_sentence = _shorten_sentence(bullet_seed, max_words=20)
        if bullet_sentence:
            return _fit_summary_layout(bullet_sentence, allow_single_word_wrap=True)

    return ""


def _summary_primary_clause(text: str) -> str:
    """Prefer the first clause to reduce clipped trailing fragments in summaries."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    parts = re.split(r"[,;\u2014]\s*", cleaned, maxsplit=1)
    primary = parts[0].strip()
    return primary or cleaned


def _collect_selected_skill_signals(experience: Experience) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for bullet in experience.bullets:
        for skill in bullet.skills:
            cleaned = skill.strip()
            lowered = cleaned.lower()
            if not cleaned or lowered in seen:
                continue
            seen.add(lowered)
            ordered.append(cleaned)
            if len(ordered) >= 2:
                return ordered

    for skill in experience.related_skills:
        cleaned = skill.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(cleaned)
        if len(ordered) >= 2:
            return ordered
    return ordered


def _target_summary_label(resume: ResumeIR) -> str:
    target_role = str(resume.target_role).strip()
    if target_role:
        return target_role
    if resume.job_context is not None:
        role_hint = str(resume.job_context.role_hint).strip()
        if role_hint:
            return role_hint
    return "the target role"


def _shorten_sentence(text: str, *, max_words: int) -> str:
    words = text.strip().replace("\n", " ").split()
    if not words:
        return ""
    clipped = _trim_trailing_fragment_words(words[:max_words])
    if not clipped:
        return ""
    sentence = " ".join(clipped).strip(" ,;:")
    if sentence and sentence[-1] not in ".!?":
        sentence = f"{sentence}."
    return sentence


def _trim_trailing_fragment_words(words: list[str]) -> list[str]:
    trimmed = list(words)
    while trimmed:
        token = trimmed[-1].strip(" ,;:.!?").lower()
        if token and token not in _TRAILING_FRAGMENT_WORDS:
            break
        trimmed.pop()
    return trimmed


def _summary_wrap_lines(
    summary: str, *, line_width: int = SUMMARY_LINE_WIDTH
) -> list[str]:
    raw_words = summary.split()
    if not raw_words:
        return []

    words: list[str] = []
    for raw_word in raw_words:
        if len(raw_word) <= line_width:
            words.append(raw_word)
            continue
        words.extend(
            textwrap.wrap(
                raw_word,
                width=line_width,
                break_long_words=True,
                break_on_hyphens=False,
            )
        )

    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > line_width:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return lines


def _fit_summary_layout(summary: str, *, allow_single_word_wrap: bool = False) -> str:
    words = summary.strip().replace("\n", " ").split()
    if not words:
        return ""

    while len(words) > SUMMARY_MAX_WORDS:
        words.pop()

    while words:
        words = _trim_trailing_fragment_words(words)
        if not words:
            return ""
        candidate = " ".join(words).strip(" ,;:")
        if candidate and candidate[-1] not in ".!?":
            candidate = f"{candidate}."
        lines = _summary_wrap_lines(candidate)
        if len(lines) > SUMMARY_MAX_LINES:
            words.pop()
            continue
        if (
            not allow_single_word_wrap
            and len(lines) > 1
            and any(len(line.split()) == 1 for line in lines[1:])
        ):
            words.pop()
            continue
        return candidate

    return ""


def _apply_rule_based_trimming(
    *,
    experiences: tuple[Experience, ...],
    enrichment_by_bullet_id: dict[str, dict[str, object]],
    max_bullet_lines: int,
    removal_reasons: dict[str, str] | None = None,
) -> tuple[Experience, ...]:
    selected_by_experience = [list(experience.bullets) for experience in experiences]

    _drop_duplicate_bullets(
        selected_by_experience,
        removal_reasons=removal_reasons,
    )
    _limit_action_word_repetition(
        selected_by_experience,
        enrichment_by_bullet_id=enrichment_by_bullet_id,
        removal_reasons=removal_reasons,
    )
    _enforce_bullet_line_budget(
        selected_by_experience,
        enrichment_by_bullet_id=enrichment_by_bullet_id,
        max_bullet_lines=max_bullet_lines,
        removal_reasons=removal_reasons,
    )

    trimmed_experiences: list[Experience] = []
    for experience, selected_bullets in zip(
        experiences, selected_by_experience, strict=True
    ):
        trimmed_experiences.append(
            Experience(
                id=experience.id,
                job_title=experience.job_title,
                company=experience.company,
                start_date=experience.start_date,
                end_date=experience.end_date,
                general_role_description=experience.general_role_description,
                related_skills=experience.related_skills,
                bullets=tuple(selected_bullets),
            )
        )
    return tuple(trimmed_experiences)


def _drop_duplicate_bullets(
    selected_by_experience: list[list[Bullet]],
    *,
    removal_reasons: dict[str, str] | None = None,
) -> None:
    seen_texts: set[str] = set()
    for bullets in selected_by_experience:
        filtered: list[Bullet] = []
        for i, bullet in enumerate(bullets):
            normalized_text = " ".join(bullet.text.lower().split())
            # Always keep the first bullet, even if duplicated.
            # For subsequent bullets, drop if already seen AND we can afford to drop
            # (still have more than the minimum required).
            if (
                i > 0
                and normalized_text in seen_texts
                and len(filtered) >= DEFAULT_MIN_BULLETS_PER_EXPERIENCE
            ):
                if removal_reasons is not None:
                    removal_reasons[bullet.id] = "duplicate"
                continue
            filtered.append(bullet)
            seen_texts.add(normalized_text)
        bullets[:] = filtered


def _limit_action_word_repetition(
    selected_by_experience: list[list[Bullet]],
    *,
    enrichment_by_bullet_id: dict[str, dict[str, object]],
    removal_reasons: dict[str, str] | None = None,
) -> None:
    occurrences: dict[str, list[tuple[int, int, Bullet]]] = {}
    for exp_index, bullets in enumerate(selected_by_experience):
        for bullet_index, bullet in enumerate(bullets):
            action_word = _extract_action_word(bullet.text)
            if not action_word:
                continue
            occurrences.setdefault(action_word, []).append(
                (exp_index, bullet_index, bullet)
            )

    for bullets_for_word in occurrences.values():
        removable = [
            candidate
            for candidate in bullets_for_word
            if len(selected_by_experience[candidate[0]])
            > DEFAULT_MIN_BULLETS_PER_EXPERIENCE
        ]
        removable.sort(
            key=lambda candidate: (
                _bullet_confidence(candidate[2], enrichment_by_bullet_id),
                candidate[0],
                candidate[1],
            )
        )
        extras_to_remove = max(
            0,
            len(bullets_for_word) - DEFAULT_MAX_ACTION_WORD_OCCURRENCES,
        )
        for exp_index, _, bullet in removable[:extras_to_remove]:
            current = selected_by_experience[exp_index]
            if len(current) <= DEFAULT_MIN_BULLETS_PER_EXPERIENCE:
                continue
            updated = [existing for existing in current if existing.id != bullet.id]
            if removal_reasons is not None and len(updated) < len(current):
                removal_reasons[bullet.id] = "action_word_cap"
            selected_by_experience[exp_index] = updated


def _estimate_wrapped_line_count(text: str, line_width: int) -> int:
    """Estimate wrapped line count by delegating to the shared wrap helper."""
    if not text.strip():
        return 1
    if line_width <= 0:
        return 1

    wrapped_lines = len(_summary_wrap_lines(text, line_width=line_width))
    # Guard against any future wrap-helper regressions by ensuring very long
    # unbroken tokens always consume at least ceil(len(token) / width) lines.
    long_token_lines = max(
        (math.ceil(len(token) / line_width) for token in text.split()),
        default=1,
    )
    return max(1, wrapped_lines, long_token_lines)


def _estimate_total_bullet_lines(selected_by_experience: list[list[Bullet]]) -> int:
    return sum(
        _estimate_wrapped_line_count(bullet.text, DEFAULT_BULLET_LINE_WIDTH)
        for bullets in selected_by_experience
        for bullet in bullets
    )


def _compute_bullet_line_budget(resume: ResumeIR) -> int:
    """Estimate the bullet-line ceiling from non-bullet layout pressure.

    Models the actual rendered vertical extent (in PDF points) of every
    non-bullet element and converts the remaining space into a bullet-line
    count at the bullet leading of PDF_BULLET_LINE_PT.

    This budget is a ceiling, not a fill target; downstream selection never
    adds bullets solely because budget remains.
    """
    # Header block: name (h1), contact line, linkedin line, header divider.
    header_pt = (
        PDF_H1_PT
        + PDF_BODY_LINE_PT  # contact
        + PDF_BODY_LINE_PT  # linkedin
        + PDF_HEADER_DIVIDER_PT
    )
    title_pt = PDF_TITLE_PT
    # Budget runs BEFORE summarize_profile_for_role, which generates a final
    # profile summary up to PROFILE_SUMMARY_MAX_LINES wrap lines. Always
    # reserve the full max so we don't under-budget the rendered summary
    # block when the generator expands a short input summary.
    summary_pt = PDF_BODY_LINE_PT * PROFILE_SUMMARY_MAX_LINES

    section_header_pt = PDF_H2_PT  # Key Skills
    section_header_pt += PDF_H2_PT  # Professional Experience
    if resume.cross_org_architectural_leadership:
        section_header_pt += PDF_H2_PT
    if resume.selected_achievements:
        section_header_pt += PDF_H2_PT
    if resume.independent_projects:
        section_header_pt += PDF_H2_PT
    if resume.profile.education_entries:
        section_header_pt += PDF_H2_PT
    if resume.profile.leadership_community_entries:
        section_header_pt += PDF_H2_PT

    # Budget runs BEFORE select_skills, which packs the skills section to the
    # TARGET_LINES_MIN..TARGET_LINES_MAX range from scripts/select_skills.py.
    # Use TARGET_LINES_MAX as the upper bound rather than measuring the
    # un-packed pre-stage skills (which is roughly 2-3x larger and inflates
    # non_bullet_pt by ~150-220pt).
    skills_pt = PDF_BODY_LINE_PT * _SKILLS_TARGET_LINES_MAX

    # Cross-org and selected-achievement lists render as bulleted paragraphs in
    # the templates (lh = PDF_BULLET_LINE_PT), not body paragraphs.
    cross_org_pt = PDF_BULLET_LINE_PT * sum(
        _estimate_wrapped_line_count(item.text, DEFAULT_BULLET_LINE_WIDTH)
        for item in resume.cross_org_architectural_leadership
    )
    selected_achievement_pt = PDF_BULLET_LINE_PT * sum(
        _estimate_wrapped_line_count(item.text, DEFAULT_BULLET_LINE_WIDTH)
        for item in resume.selected_achievements
    )
    independent_project_pt = 0.0
    for project in resume.independent_projects:
        independent_project_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
            project.name, DEFAULT_BULLET_LINE_WIDTH
        )
        if project.summary.strip():
            independent_project_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
                project.summary, DEFAULT_BULLET_LINE_WIDTH
            )

    role_header_pt = 0.0
    company_blocks = _company_block_ranges(resume.experiences)

    for exp_index, experience in enumerate(resume.experiences):
        if exp_index in company_blocks:
            role_header_pt += PDF_COMPANY_LINE_BLOCK_PT
        role_header_pt += PDF_H3_PT  # job-title-line (h3)
        # Budget runs BEFORE summarize_for_role, which caps role descriptions
        # at SUMMARY_MAX_LINES (2) wrap-lines in the SUMMARY_LINE_WIDTH (72)
        # column. Re-rendered at full content width that's ≤2 lines, so cap
        # the wrap-line count at SUMMARY_MAX_LINES rather than measuring the
        # pre-stage long enriched description directly. Skip the cost when
        # general_role_description is empty so the renderer's "no role-summary
        # paragraph rendered" path matches the budget — needed for compressed
        # mode's freed-space credit (PR #278 review). Without this guard
        # _estimate_wrapped_line_count("") returns 1, so an empty description
        # would still cost PDF_BODY_LINE_PT and the credit wouldn't apply.
        if experience.general_role_description.strip():
            role_header_pt += PDF_BODY_LINE_PT * min(
                SUMMARY_MAX_LINES,
                _estimate_wrapped_line_count(
                    experience.general_role_description,
                    DEFAULT_BULLET_LINE_WIDTH,
                ),
            )

    education_pt = 0.0
    for education_item in resume.profile.education_entries:
        education_pt += PDF_BODY_LINE_PT  # degree
        metadata = " | ".join(
            part
            for part in [
                education_item.institution,
                education_item.location,
                education_item.date_range,
            ]
            if part.strip()
        )
        if metadata:
            education_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
                metadata,
                DEFAULT_BULLET_LINE_WIDTH,
            )
        if education_item.notes.strip():
            education_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
                education_item.notes,
                DEFAULT_BULLET_LINE_WIDTH,
            )

    leadership_pt = 0.0
    for leadership_item in resume.profile.leadership_community_entries:
        header = " | ".join(
            part
            for part in [
                leadership_item.title,
                leadership_item.organization,
                leadership_item.date_range,
            ]
            if part.strip()
        )
        if header:
            leadership_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
                header,
                DEFAULT_BULLET_LINE_WIDTH,
            )
        if leadership_item.details.strip():
            leadership_pt += PDF_BODY_LINE_PT * _estimate_wrapped_line_count(
                leadership_item.details,
                DEFAULT_BULLET_LINE_WIDTH,
            )

    non_bullet_pt = (
        header_pt
        + title_pt
        + summary_pt
        + section_header_pt
        + skills_pt
        + cross_org_pt
        + selected_achievement_pt
        + independent_project_pt
        + role_header_pt
        + education_pt
        + leadership_pt
    )

    minimum_floor_lines = _estimate_minimum_required_bullet_lines(resume.experiences)
    available_bullet_pt = DEFAULT_TWO_PAGE_PT_BUDGET - non_bullet_pt
    available_bullet_lines = int(available_bullet_pt // PDF_BULLET_LINE_PT)
    computed_budget = max(minimum_floor_lines, available_bullet_lines)

    # Keep the historical hard ceiling as a deterministic safety cap. This
    # allows tests/config to force an intentionally strict cap and verify
    # floor warnings.
    capped_budget = max(1, min(DEFAULT_MAX_BULLET_LINES, computed_budget))
    logger.debug(
        "Computed bullet-line budget=%s (non_bullet_pt=%.1f, floor=%s)",
        capped_budget,
        non_bullet_pt,
        minimum_floor_lines,
    )
    return capped_budget


def _estimate_minimum_required_bullet_lines(experiences: tuple[Experience, ...]) -> int:
    """Estimate minimum bullet lines needed to satisfy per-experience bullet floor."""
    total = 0
    for experience in experiences:
        if not experience.bullets:
            continue
        line_counts = sorted(
            _estimate_wrapped_line_count(bullet.text, DEFAULT_BULLET_LINE_WIDTH)
            for bullet in experience.bullets
        )
        keep_count = min(DEFAULT_MIN_BULLETS_PER_EXPERIENCE, len(line_counts))
        total += sum(line_counts[:keep_count])
    return total


def _enforce_bullet_line_budget(
    selected_by_experience: list[list[Bullet]],
    *,
    enrichment_by_bullet_id: dict[str, dict[str, object]],
    max_bullet_lines: int,
    removal_reasons: dict[str, str] | None = None,
) -> None:
    while _estimate_total_bullet_lines(selected_by_experience) > max_bullet_lines:
        candidates: list[tuple[float, int, int, Bullet]] = []
        for exp_index, bullets in enumerate(selected_by_experience):
            if len(bullets) <= DEFAULT_MIN_BULLETS_PER_EXPERIENCE:
                continue
            for bullet_index, bullet in enumerate(bullets):
                candidates.append(
                    (
                        _bullet_confidence(bullet, enrichment_by_bullet_id),
                        exp_index,
                        bullet_index,
                        bullet,
                    )
                )
        if not candidates:
            remaining_lines = _estimate_total_bullet_lines(selected_by_experience)
            if remaining_lines > max_bullet_lines:
                logging.warning(
                    "Line-budget target not reached: estimated bullet lines=%s exceeds max=%s because all experiences are at the minimum bullets floor (%s).",
                    remaining_lines,
                    max_bullet_lines,
                    DEFAULT_MIN_BULLETS_PER_EXPERIENCE,
                )
            return

        # Sort: lowest confidence first; when tied, prefer trimming older roles
        # (highest exp_index) and last bullets first (highest bullet_index).
        candidates.sort(key=lambda c: (c[0], -c[1], -c[2]))
        _, exp_index, _, bullet_to_remove = candidates[0]
        current = selected_by_experience[exp_index]
        selected_by_experience[exp_index] = [
            bullet for bullet in current if bullet.id != bullet_to_remove.id
        ]
        if removal_reasons is not None:
            removal_reasons[bullet_to_remove.id] = "line_budget"


def _extract_action_word(text: str) -> str:
    for token in text.split():
        cleaned = "".join(
            character for character in token.lower() if character.isalpha()
        )
        if cleaned:
            return cleaned
    return ""


def _bullet_confidence(
    bullet: Bullet, enrichment_by_bullet_id: dict[str, dict[str, object]]
) -> float:
    metadata = enrichment_by_bullet_id.get(bullet.id, {})
    if not isinstance(metadata, dict):
        return 0.0
    return _coerce_relevance_score(metadata.get("confidence"))


def _html_escape(value: str) -> str:
    return html.escape(value, quote=True)


def _render_contact_html(profile: Profile) -> str:
    items = [
        profile.location,
        profile.email,
        profile.phone,
        profile.website,
        _build_linkedin_url(profile.linkedin),
        _build_github_url(profile.github),
    ]
    filtered = [item for item in items if item.strip()]
    return " | ".join(_html_escape(item) for item in filtered)


def _render_contact_markdown(profile: Profile) -> str:
    items: list[str] = []

    if profile.location.strip():
        items.append(profile.location)
    if profile.email.strip():
        items.append(f"[{profile.email}](mailto:{profile.email})")
    if profile.phone.strip():
        items.append(profile.phone)
    if profile.website.strip():
        website = profile.website.strip()
        website_href = website
        if not website.startswith(("http://", "https://")):
            website_href = f"https://{website}"
        items.append(f"[{website}]({website_href})")

    linkedin_url = _build_linkedin_url(profile.linkedin)
    if linkedin_url:
        items.append(f"[{linkedin_url}](https://{linkedin_url})")

    github_url = _build_github_url(profile.github)
    if github_url:
        items.append(f"[{github_url}](https://{github_url})")

    return " | ".join(items)


def _format_month_year(raw: str) -> str:
    """Format YYYY-MM as Month YYYY while preserving non-standard values."""
    value = raw.strip()
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not match:
        return value
    year = int(match.group(1))
    month = int(match.group(2))
    month_names = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    if 1 <= month <= 12:
        return f"{month_names[month - 1]} {year}"
    return value


def _coerce_year_month(raw: str, *, is_end: bool) -> tuple[int, int] | None:
    value = raw.strip()
    if not value:
        return None
    lowered = value.lower()
    if lowered in {"present", "current", "now"}:
        return (9999, 12) if is_end else (0, 1)
    match = re.fullmatch(r"(\d{4})-(\d{2})", value)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if month < 1 or month > 12:
        return None
    return year, month


def _date_sort_key(raw: str, *, is_end: bool) -> tuple[int, int]:
    """Sort key for yyyy-mm dates, treating 'Present' as far-future for end dates."""
    return _coerce_year_month(raw, is_end=is_end) or (0, 1)


def _current_year_month() -> tuple[int, int]:
    from datetime import date

    today = date.today()
    return today.year, today.month


def _parse_year_month(raw: str, *, is_end: bool) -> tuple[int, int] | None:
    return _coerce_year_month(raw, is_end=is_end)


def _is_older_than_years(
    year_month: tuple[int, int], *, years: int, reference: tuple[int, int]
) -> bool:
    ref_year, ref_month = reference
    year, month = year_month
    month_delta = (ref_year - year) * 12 + (ref_month - month)
    return month_delta > (years * 12)


def _baseline_resume_for_fit_assessment(resume: ResumeIR) -> ResumeIR:
    """Restrict ``resume.experiences`` to those within the recency window.

    The fit_assessment LLM call should only score experiences that can
    actually appear on the rendered resume — including out-of-window roles
    inflates the prompt, biases the overall score with content the reader
    never sees, and increases failure risk on long histories. The filter
    mirrors the same recency rule ``_prepare_display_experiences`` uses,
    but keeps every kept experience's full canonical bullet set (the LLM
    must score against untrimmed content).
    """
    reference = _current_year_month()
    in_window = []
    for experience in resume.experiences:
        parsed_end = _parse_year_month(experience.end_date, is_end=True)
        if parsed_end is not None and _is_older_than_years(
            parsed_end,
            years=EXPERIENCE_DISPLAY_RECENCY_YEARS,
            reference=reference,
        ):
            continue
        in_window.append(experience)
    if len(in_window) == len(resume.experiences):
        return resume
    return dc_replace(resume, experiences=tuple(in_window))


def _prepare_display_experiences(resume: ResumeIR) -> tuple[Experience, ...]:
    """Filter/rank rendered experiences while preserving deterministic ordering."""
    reference = _current_year_month()
    ranked: list[tuple[tuple[float, int, int, int, int], int, Experience]] = []

    for index, experience in enumerate(resume.experiences):
        parsed_end = _parse_year_month(experience.end_date, is_end=True)
        if parsed_end is not None and _is_older_than_years(
            parsed_end,
            years=EXPERIENCE_DISPLAY_RECENCY_YEARS,
            reference=reference,
        ):
            continue

        parsed_start = _parse_year_month(experience.start_date, is_end=False)
        confidence_values = [
            _bullet_confidence(bullet, resume.enrichment_by_bullet_id)
            for bullet in experience.bullets
        ]
        relevance_score = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values
            else 0.0
        )

        end_year, end_month = parsed_end or (0, 0)
        start_year, start_month = parsed_start or (0, 0)
        sort_key = (
            -relevance_score,
            -end_year,
            -end_month,
            -start_year,
            -start_month,
        )
        ranked.append((sort_key, index, experience))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return tuple(experience for _, _, experience in ranked)


def _apply_display_experience_selection(resume: ResumeIR) -> ResumeIR:
    display_experiences = _prepare_display_experiences(resume)
    kept_bullet_ids = {
        bullet.id for experience in display_experiences for bullet in experience.bullets
    }
    filtered_enrichment = {
        bullet_id: metadata
        for bullet_id, metadata in resume.enrichment_by_bullet_id.items()
        if bullet_id in kept_bullet_ids
    }
    return dc_replace(
        resume,
        experiences=display_experiences,
        enrichment_by_bullet_id=filtered_enrichment,
    )


def _format_date_range(start_raw: str, end_raw: str) -> str:
    return f"{_format_month_year(start_raw)} - {_format_month_year(end_raw)}"


def _normalize_company_alias(company: str) -> str:
    """Normalize company aliases so equivalent labels group together."""
    normalized = re.sub(r"[^a-z0-9]+", " ", company.strip().lower()).strip()
    hp_poly_aliases = {
        "hp poly",
        "hp polycom",
        "hp poly formerly polycom",
        "poly",
        "polycom",
        "hp poly formerly polycom austin tx",
    }
    if normalized in hp_poly_aliases:
        return "hp_poly"
    return normalized


def _company_block_ranges(
    experiences: Sequence[Experience],
) -> dict[int, tuple[int, int]]:
    """Return start/end index ranges for contiguous same-company experience blocks."""
    company_blocks: dict[int, tuple[int, int]] = {}
    block_start = 0
    while block_start < len(experiences):
        block_end = block_start
        while block_end + 1 < len(experiences) and _normalize_company_alias(
            experiences[block_end + 1].company
        ) == _normalize_company_alias(experiences[block_start].company):
            block_end += 1
        company_blocks[block_start] = (block_start, block_end)
        block_start = block_end + 1
    return company_blocks


def _display_company_header(company: str) -> str:
    """Return display text for company group headers."""
    canonical = company.strip()
    if _normalize_company_alias(canonical) == "hp_poly":
        return "HP / Poly (formerly Polycom), Austin, TX"
    return canonical


def _slugify_output_label(value: str) -> str:
    """Normalize artifact labels for cross-platform filenames."""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def _build_artifact_prefix(*, processing_mode: str) -> str:
    """Return the single company-agnostic artifact prefix for this mode."""
    mode_suffix = "processed" if processing_mode == "processed" else "raw"
    return f"latest_resume_{mode_suffix}"


def _secondary_template_prefix(output_prefix: str, secondary_template: str) -> str:
    """Return the secondary HTML prefix derived from a primary prefix.
    Splits on the *last* _resume_ segment so that company slugs which
    themselves contain the word "resume" (e.g. resume_corp_resume_raw) are
    not mangled.
    """
    base, _, mode_suffix = output_prefix.rpartition("_resume_")
    if not base:
        # Fallback: prefix has no "_resume_" token; append template name.
        return f"{output_prefix}_{secondary_template}"
    return f"{base}_{secondary_template}_resume_{mode_suffix}"


def render_html(
    resume: ResumeIR, output_path: Path, template_name: str = "default"
) -> None:
    contact_line = _render_contact_html(resume.profile)

    experiences_html: list[str] = []
    company_blocks = _company_block_ranges(resume.experiences)

    for exp_index, exp in enumerate(resume.experiences):
        compressed = exp.compression == "compressed"
        if compressed:
            # Compressed render: title + dates + single highest-relevance bullet
            # (#271). Skip role-summary and related-skills paragraphs so the
            # entry shrinks while preserving chronology.
            visible_bullets = exp.bullets[:1]
        else:
            visible_bullets = exp.bullets
        bullets_html = "\n".join(
            f"<li>{_html_escape(bullet.text)}</li>" for bullet in visible_bullets
        )
        if compressed:
            related_html = ""
        else:
            related = ", ".join(_html_escape(skill) for skill in exp.related_skills)
            related_html = (
                f'<p class="related-skills"><strong>Related skills:</strong> {related}</p>'
                if related
                else ""
            )
        company_header_html = ""
        if exp_index in company_blocks:
            start_index, end_index = company_blocks[exp_index]
            block = resume.experiences[start_index : end_index + 1]
            overall_start = min(
                block, key=lambda item: _date_sort_key(item.start_date, is_end=False)
            ).start_date
            overall_end = max(
                block, key=lambda item: _date_sort_key(item.end_date, is_end=True)
            ).end_date
            company_header_html = (
                f'<p class="company-line"><strong>{_html_escape(_display_company_header(exp.company))}</strong>'
                f"<span>{_html_escape(_format_date_range(overall_start, overall_end))}</span></p>"
            )

        role_date_range = _format_date_range(exp.start_date, exp.end_date)
        lines = ['<section class="experience-item">']
        if company_header_html:
            lines.append(company_header_html)
        title_line = (
            f'<h3 class="job-title-line">{_html_escape(exp.job_title)}'
            f"<span>{_html_escape(role_date_range)}</span></h3>"
        )
        lines.append(title_line)
        if not compressed:
            # Suppress the role-summary <p> entirely when the description
            # is empty/whitespace so an empty paragraph doesn't render
            # (and so the bullet-line budget — which gives empty descriptions
            # zero cost since round-11 — matches what the renderer actually
            # emits). PR #278 review.
            if exp.general_role_description.strip():
                lines.append(
                    f'<p class="role-summary">'
                    f"{_html_escape(exp.general_role_description)}</p>"
                )
            lines.append(related_html)
        if visible_bullets:
            lines.extend(["<ul>", bullets_html, "</ul>"])
        lines.append("</section>")
        experiences_html.append("\n".join(lines))

    skills_html: list[str] = []
    for category, skills in resume.skills_by_category.items():
        joined_skills = join_skills(_html_escape(skill) for skill in skills)
        skills_html.append(
            f'<p class="skills-category"><strong>{_html_escape(category)}:</strong> {joined_skills}</p>'
        )

    education_html: list[str] = []
    for education_item in resume.profile.education_entries:
        metadata = " | ".join(
            part
            for part in [
                education_item.institution,
                education_item.location,
                education_item.date_range,
            ]
            if part.strip()
        )
        education_html.append(
            "\n".join(
                [
                    '<section class="info-item">',
                    f"<p><strong>{_html_escape(education_item.degree)}</strong></p>",
                    f"<p>{_html_escape(metadata)}</p>" if metadata else "",
                    (
                        f"<p>{_html_escape(education_item.notes)}</p>"
                        if education_item.notes.strip()
                        else ""
                    ),
                    "</section>",
                ]
            )
        )

    leadership_html: list[str] = []
    for leadership_item in resume.profile.leadership_community_entries:
        header_parts = [
            leadership_item.title,
            leadership_item.organization,
            leadership_item.date_range,
        ]
        header = " | ".join(part for part in header_parts if part.strip())
        leadership_html.append(
            "\n".join(
                [
                    '<section class="info-item">',
                    f"<p><strong>{_html_escape(header)}</strong></p>" if header else "",
                    (
                        f"<p>{_html_escape(leadership_item.details)}</p>"
                        if leadership_item.details.strip()
                        else ""
                    ),
                    "</section>",
                ]
            )
        )

    cross_org_html: list[str] = []
    for cross_org_entry in resume.cross_org_architectural_leadership:
        cross_org_html.append(
            "\n".join(
                [
                    '<section class="info-item">',
                    "<ul>",
                    f"<li>{_html_escape(cross_org_entry.text)}</li>",
                    "</ul>",
                    "</section>",
                ]
            )
        )

    selected_achievements_html: list[str] = []
    for selected_achievement in resume.selected_achievements:
        selected_achievements_html.append(
            "\n".join(
                [
                    '<section class="info-item">',
                    "<ul>",
                    f"<li>{_html_escape(selected_achievement.text)}</li>",
                    "</ul>",
                    "</section>",
                ]
            )
        )

    independent_projects_html: list[str] = []
    for project in resume.independent_projects:
        if project.url.strip():
            name_inner = (
                f'<a href="{_html_escape(project.url)}">'
                f"{_html_escape(project.name)}</a>"
            )
        else:
            name_inner = _html_escape(project.name)
        independent_projects_html.append(
            "\n".join(
                [
                    '<section class="info-item">',
                    f"<p><strong>{name_inner}</strong></p>",
                    (
                        f"<p>{_html_escape(project.summary)}</p>"
                        if project.summary.strip()
                        else ""
                    ),
                    "</section>",
                ]
            )
        )

    template = get_template(template_name)
    context = TemplateContext(
        name=resume.profile.name,
        headline=resume.display_headline,
        contact_html=contact_line,
        target_role=resume.target_role,
        target_company=resume.target_company,
        resume_title=derive_resume_title(resume),
        summary=resume.profile.summary,
        skills_html=skills_html,
        experiences_html=experiences_html,
        education_html=education_html,
        leadership_html=leadership_html,
        cross_org_html=cross_org_html,
        selected_achievements_html=selected_achievements_html,
        independent_projects_html=independent_projects_html,
    )
    output_path.write_text(template.render(context), encoding="utf-8")


def render_markdown(resume: ResumeIR, output_path: Path) -> None:
    lines: list[str] = [
        f"# {resume.profile.name}",
        "",
        resume.display_headline,
        "",
        _render_contact_markdown(resume.profile),
        "",
    ]

    lines.extend(
        [
            "## Summary",
            "",
            resume.profile.summary,
            "",
            "## Key Skills and Expertise",
            "",
        ]
    )

    for category, skills in resume.skills_by_category.items():
        lines.append(f"- **{category}:** {join_skills(skills)}")

    if resume.cross_org_architectural_leadership:
        lines.extend(["", "## Cross-Org Architectural Leadership", ""])
        for cross_org_entry in resume.cross_org_architectural_leadership:
            lines.append(f"- {cross_org_entry.text}")

    if resume.selected_achievements:
        lines.extend(["", "## Selected Achievements", ""])
        for selected_achievement in resume.selected_achievements:
            lines.append(f"- {selected_achievement.text}")

    if resume.independent_projects:
        lines.extend(["", "## Independent Projects", ""])
        for project in resume.independent_projects:
            if project.url.strip():
                lines.append(f"- **[{project.name}]({project.url})**")
            else:
                lines.append(f"- **{project.name}**")
            if project.summary.strip():
                lines.append(f"  - {project.summary}")

    lines.extend(["", "## Professional Experience", ""])

    for exp in resume.experiences:
        compressed = exp.compression == "compressed"
        if compressed:
            # Compressed render: title + dates + single highest-relevance bullet.
            # Skip role-summary and related-skills lines so the entry shrinks
            # to the minimum visible signal while preserving chronology (#271).
            lines.extend(
                [
                    f"### {exp.job_title} | {exp.company}",
                    f"{exp.start_date} - {exp.end_date}",
                    "",
                ]
            )
            if exp.bullets:
                lines.append(f"- {exp.bullets[0].text}")
            lines.append("")
            continue
        lines.extend(
            [
                f"### {exp.job_title} | {exp.company}",
                f"{exp.start_date} - {exp.end_date}",
                "",
            ]
        )
        # Match the budget's "empty description costs 0 lines" credit (round-11)
        # by skipping the description block in markdown when blank, mirroring
        # the same suppression in render_html. PR #278 review.
        if exp.general_role_description.strip():
            lines.extend([exp.general_role_description, ""])
        if exp.related_skills:
            lines.extend(
                [
                    "Related skills: " + ", ".join(exp.related_skills),
                    "",
                ]
            )
        for bullet in exp.bullets:
            lines.append(f"- {bullet.text}")
        lines.append("")

    if resume.profile.education_entries:
        lines.extend(["", "## Education", ""])
        for education_item in resume.profile.education_entries:
            lines.append(f"- **{education_item.degree}**")
            metadata = " | ".join(
                part
                for part in [
                    education_item.institution,
                    education_item.location,
                    education_item.date_range,
                ]
                if part.strip()
            )
            if metadata:
                lines.append(f"  - {metadata}")
            if education_item.notes.strip():
                lines.append(f"  - {education_item.notes}")

    if resume.profile.leadership_community_entries:
        lines.extend(["", "## Leadership & Community", ""])
        for leadership_item in resume.profile.leadership_community_entries:
            header = " | ".join(
                part
                for part in [
                    leadership_item.title,
                    leadership_item.organization,
                    leadership_item.date_range,
                ]
                if part.strip()
            )
            lines.append(f"- **{header}**" if header else "-")
            if leadership_item.details.strip():
                lines.append(f"  - {leadership_item.details}")

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_ir_snapshot(resume: ResumeIR, output_path: Path) -> None:
    payload: dict[str, Any] = {
        "target_role": resume.target_role,
        "target_company": resume.target_company,
        "profile": {
            "name": resume.profile.name,
            "headline": resume.profile.headline,
            "display_headline": resume.display_headline,
            "location": resume.profile.location,
            "email": resume.profile.email,
            "phone": resume.profile.phone,
            "website": resume.profile.website,
            "linkedin": resume.profile.linkedin,
            "linkedin_url": _build_linkedin_url(resume.profile.linkedin),
            "github": resume.profile.github,
            "github_url": _build_github_url(resume.profile.github),
            "summary": resume.profile.summary,
            "education_count": len(resume.profile.education_entries),
            "leadership_community_count": len(
                resume.profile.leadership_community_entries
            ),
        },
        "experience_count": len(resume.experiences),
        "bullet_count": sum(len(exp.bullets) for exp in resume.experiences),
        "skills_category_count": len(resume.skills_by_category),
        "skills_count": sum(
            len(skills) for skills in resume.skills_by_category.values()
        ),
        "enrichment_count": len(resume.enrichment_by_bullet_id),
        "cross_org_architectural_leadership_count": len(
            resume.cross_org_architectural_leadership
        ),
        "selected_achievements_count": len(resume.selected_achievements),
        "independent_projects_count": len(resume.independent_projects),
        "independent_projects_visibility": resume.independent_projects_visibility,
    }
    if resume.job_context is not None:
        payload["job_context"] = resume.job_context.to_dict()
    if resume.enrichment_by_bullet_id:
        payload["bullet_enrichment"] = resume.enrichment_by_bullet_id
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_text_snapshot(resume: ResumeIR, output_path: Path) -> None:
    """Write a plain-text snapshot optimized for low-noise git diffs."""
    lines: list[str] = [
        f"target_role: {resume.target_role}",
        f"target_company: {resume.target_company}",
        f"profile.name: {resume.profile.name}",
        f"profile.headline: {resume.profile.headline}",
        f"profile.display_headline: {resume.display_headline}",
        f"profile.location: {resume.profile.location}",
        f"profile.email: {resume.profile.email}",
        f"profile.phone: {resume.profile.phone}",
        f"profile.website: {resume.profile.website}",
        f"profile.linkedin: {resume.profile.linkedin}",
        f"profile.linkedin_url: {_build_linkedin_url(resume.profile.linkedin)}",
        f"profile.github: {resume.profile.github}",
        f"profile.github_url: {_build_github_url(resume.profile.github)}",
        "",
        "summary:",
        resume.profile.summary,
        "",
        "skills:",
    ]

    # Sort categories for stable diffs if CSV section ordering changes.
    for category in sorted(resume.skills_by_category):
        skills = resume.skills_by_category[category]
        lines.append(f"- {category}: {join_skills(skills)}")

    lines.extend(
        [
            "",
            f"experience_count: {len(resume.experiences)}",
            f"bullet_count: {sum(len(exp.bullets) for exp in resume.experiences)}",
            "",
            "experience:",
        ]
    )

    for exp in resume.experiences:
        lines.extend(
            [
                f"- {exp.job_title} | {exp.company}",
                f"  date_range: {exp.start_date} - {exp.end_date}",
                f"  compression: {exp.compression}",
                f"  role_summary: {exp.general_role_description}",
                f"  related_skills: {', '.join(exp.related_skills)}",
            ]
        )
        lines.extend(f"  * {bullet.text}" for bullet in exp.bullets)

    lines.extend(["", "education:"])
    for education_item in resume.profile.education_entries:
        lines.extend(
            [
                f"- degree: {education_item.degree}",
                f"  institution: {education_item.institution}",
                f"  location: {education_item.location}",
                f"  date_range: {education_item.date_range}",
                f"  notes: {education_item.notes}",
            ]
        )

    lines.extend(["", "leadership_community:"])
    for leadership_item in resume.profile.leadership_community_entries:
        lines.extend(
            [
                f"- title: {leadership_item.title}",
                f"  organization: {leadership_item.organization}",
                f"  date_range: {leadership_item.date_range}",
                f"  details: {leadership_item.details}",
            ]
        )

    lines.extend(["", "cross_org_architectural_leadership:"])
    if not resume.cross_org_architectural_leadership:
        lines.append("- none")
    else:
        for cross_org_entry in resume.cross_org_architectural_leadership:
            lines.extend(
                [
                    f"- text: {cross_org_entry.text}",
                    f"  source_bullet_ids: {', '.join(cross_org_entry.source_bullet_ids)}",
                ]
            )

    lines.extend(["", "selected_achievements:"])
    if not resume.selected_achievements:
        lines.append("- none")
    else:
        for selected_achievement in resume.selected_achievements:
            lines.extend(
                [
                    f"- text: {selected_achievement.text}",
                    f"  source_bullet_ids: {', '.join(selected_achievement.source_bullet_ids)}",
                ]
            )

    lines.extend(
        [
            "",
            f"independent_projects_visibility: {resume.independent_projects_visibility}",
            "independent_projects:",
        ]
    )
    if not resume.independent_projects:
        lines.append("- none")
    else:
        for project in resume.independent_projects:
            lines.extend(
                [
                    f"- name: {project.name}",
                    f"  summary: {project.summary}",
                    f"  url: {project.url}",
                    f"  key_skills: {', '.join(project.key_skills)}",
                    f"  source_bullet_ids: {', '.join(project.source_bullet_ids)}",
                ]
            )

    lines.extend(["", "job_context:"])
    if resume.job_context is None:
        lines.append("- none")
    else:
        lines.extend(
            [
                f"- source: {resume.job_context.source}",
                f"  input_url: {resume.job_context.input_url}",
                f"  fetch_status: {resume.job_context.fetch_status}",
                f"  job_id: {resume.job_context.job_id}",
                f"  role_hint: {resume.job_context.role_hint}",
                f"  company_name: {resume.job_context.company_name}",
            ]
        )
        if resume.job_context.notes:
            lines.append(f"  notes: {'; '.join(resume.job_context.notes)}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# Below this many chars of JD description, the static-HTML fetch almost
# certainly missed the JS-rendered body. Loud-warn at that point: when LLM
# tailoring is enabled the LLM stages will run on near-empty context, and
# when LLM tailoring is disabled the build is the un-tailored baseline
# regardless. See issue #247 for the underlying fetch-quality work.
_MIN_JD_DESCRIPTION_CHARS = 200


def _jd_context_below_threshold(job_context: JobContext) -> bool:
    """Shared check used by the WARNING, the gate, and the LLM-summary path.

    Returns True when the JD-ingest result is below the
    _MIN_JD_DESCRIPTION_CHARS threshold — i.e. the JD context is too
    thin to reliably tailor against. Two common causes:

    - --job-url: the static fetcher couldn't see JS-rendered content
      and only got the navigation shell.
    - --job-text-file: the user-supplied file is empty or near-empty.

    The predicate is intentionally generic about the cause; callers
    that want to surface the JS-render-specific diagnostic do so
    themselves (see _warn_if_jd_ingest_empty on the --job-url path).
    """
    excerpt_len = len(job_context.description_excerpt or "")
    return excerpt_len < _MIN_JD_DESCRIPTION_CHARS


def _warn_if_jd_ingest_empty(*, job_context: JobContext, job_url: str) -> None:
    """Print a prominent stderr warning when JD ingest looks essentially empty.

    Detection-only — does not gate the build. Threshold is conservative:
    real JDs are typically multiple paragraphs (>>200 chars), and a
    hundred-char fetch is almost always navigation shell from a JS-
    rendered job board (Workday, Workable, Greenhouse iframe, etc.)
    where the actual JD body never reached us. The printed Effect line
    branches on whether LLM tailoring is enabled so the message matches
    actual runtime behavior in both modes.
    """
    if not _jd_context_below_threshold(job_context):
        return
    excerpt_len = len(job_context.description_excerpt or "")
    if _llm_stage_enabled():
        effect_line = (
            "  Effect: LLM tailoring stages will run on near-empty context, "
            "producing a resume close to the un-tailored baseline."
        )
    else:
        effect_line = (
            "  Effect: LLM tailoring is disabled, so this build is the "
            "un-tailored baseline regardless. Set RESUME_BUILDER_LLM_ENABLED=1 "
            "(or fixture mode) to enable JD-conditioned stages — though they "
            "will also run on near-empty context until the JD body is recovered."
        )
    print(
        "WARNING: JD ingest produced little or no usable content for the "
        f"supplied --job-url ({excerpt_len} chars).\n"
        f"  URL: {job_url}\n"
        "  Likely cause: the JD body is rendered by client-side JavaScript "
        "and the static HTML fetcher only saw the navigation shell.\n"
        f"{effect_line}\n"
        "  Workaround: copy the JD text into a file and rerun with "
        "--job-text-file <path> instead of --job-url.\n"
        "  Tracking: https://github.com/jsmithpkp21/resume-builder/issues/247",
        file=sys.stderr,
    )


def _emit_jd_context_required_error(*, excerpt_len: int, source_label: str) -> None:
    """Print the --require-jd-context gate's ERROR line.

    Shared helper for both the --job-url and --job-text-file ingest
    branches. The source_label is the user-facing string that names
    the input the gate is rejecting (e.g. "--job-url <url>" or
    "--job-text-file <path>") so the operator can find which input
    came up short.
    """
    print(
        f"ERROR: --require-jd-context (or {REQUIRE_JD_CONTEXT_ENV}=1) is set "
        f"and JD ingest produced only {excerpt_len} chars (< "
        f"{_MIN_JD_DESCRIPTION_CHARS}-char threshold) from "
        f"{source_label}. Aborting with exit code "
        f"{EXIT_JD_CONTEXT_REQUIRED} rather than shipping an "
        f"un-tailored baseline resume.",
        file=sys.stderr,
    )


def _resolve_output_dir(args: argparse.Namespace) -> Path:
    """Return the application-root directory for outputs.

    When --output-dir is unset AND a non-placeholder company slug is
    available — whether JD-derived or supplied explicitly via --company —
    route to data/outputs/<slug>/. Otherwise return the user-supplied
    --output-dir value or the baseline default.
    """
    user_value: Path | None = getattr(args, "output_dir", None)
    if user_value is not None:
        return user_value
    company = getattr(args, "company", "") or ""
    if company and company != COMPANY_PLACEHOLDER_SLUG:
        slug: str = document_export.snake_case(company)
        routed = DEFAULT_OUTPUT_BASE / slug
        print(f"--output-dir auto-routed to: {routed}")
        return routed
    return DEFAULT_OUTPUT_DIR


def run_pipeline(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    experiences = load_experiences(args.experience_db)
    cross_org_architectural_leadership = load_cross_org_architectural_leadership(
        args.experience_db,
        experiences=experiences,
    )
    selected_achievements = load_selected_achievements(
        args.experience_db,
        experiences=experiences,
    )
    independent_projects, independent_projects_visibility = load_independent_projects(
        args.experience_db,
        experiences=experiences,
    )
    skills_by_category = load_skills_by_category(args.skills_matrix)
    job_url = args.job_url.strip()
    job_text_file = args.job_text_file
    has_job_url = job_url != ""
    has_job_text_file = job_text_file is not None
    if has_job_url and has_job_text_file:
        raise ValueError("Provide only one of --job-url or --job-text-file")

    job_context: JobContext | None = None
    if job_text_file is not None:
        assert_not_blocked_runtime_input(job_text_file)
        job_text = job_text_file.read_text(encoding="utf-8")
        job_context = ingest_job_text(job_text, source_hint="job-text-file")
        if _jd_context_required(args) and _jd_context_below_threshold(job_context):
            _emit_jd_context_required_error(
                excerpt_len=len(job_context.description_excerpt or ""),
                source_label=f"--job-text-file {job_text_file}",
            )
            return EXIT_JD_CONTEXT_REQUIRED
    elif has_job_url:
        job_context = ingest_job_context(job_url)
        _warn_if_jd_ingest_empty(job_context=job_context, job_url=job_url)
        if _jd_context_required(args) and _jd_context_below_threshold(job_context):
            _emit_jd_context_required_error(
                excerpt_len=len(job_context.description_excerpt or ""),
                source_label=f"--job-url {job_url}",
            )
            return EXIT_JD_CONTEXT_REQUIRED

    # When the deterministic JD extractor returned no company name, ask the
    # LLM (gated by RESUME_BUILDER_LLM_ENABLED / fixture mode). Cheap to gate:
    # the LLM cache makes repeat builds free.
    if (
        job_context is not None
        and not job_context.company_name.strip()
        and _llm_stage_enabled()
    ):
        llm_company = _extract_company_via_llm(job_context)
        if llm_company:
            job_context = dc_replace(job_context, company_name=llm_company)

    resolved_target_role = args.target_role.strip()
    if not resolved_target_role and job_context is not None:
        resolved_target_role = job_context.role_hint

    resolved_target_company = ""
    if job_context is not None:
        resolved_target_company = job_context.company_name

    # Auto-derive --company filename slug from the JD when not explicitly set.
    explicit_company = getattr(args, "company", None)
    if explicit_company is None or not explicit_company.strip():
        if job_context is not None and job_context.company_name.strip():
            args.company = job_context.company_name.strip()
            print(
                f"--company auto-derived from job description: "
                f"'{document_export.snake_case(args.company)}'"
            )
        elif job_context is not None:
            # JD was supplied but neither the deterministic regex nor the LLM
            # tier produced a company name. Fail loudly rather than silently
            # routing artifacts under data/outputs/baseline/, which would mask
            # a real extraction miss.
            raise ValueError(
                "Could not derive a company name from the supplied JD. "
                "Pass --company <slug> to override, or inspect the supplied "
                "JD (URL or file) contents."
            )
        else:
            args.company = COMPANY_PLACEHOLDER_SLUG
    else:
        args.company = explicit_company.strip()

    # Auto-route --output-dir to data/outputs/<slug>/ when default and a real
    # company slug is available. The "baseline" fallback (no JD or no
    # derivable company) is kept intentionally as the smoke-run path.
    args.output_dir = _resolve_output_dir(args)

    resume = assemble_baseline_resume(
        profile=profile,
        target_role=resolved_target_role,
        target_company=resolved_target_company,
        job_context=job_context,
        experiences=experiences,
        skills_by_category=skills_by_category,
        cross_org_architectural_leadership=cross_org_architectural_leadership,
        selected_achievements=selected_achievements,
        independent_projects=independent_projects,
        independent_projects_visibility=independent_projects_visibility,
    )
    # Apply visibility filter before processed-mode stages so suppressed
    # independent_projects do not consume layout budget in
    # _compute_bullet_line_budget() and cannot influence trim/selection.
    # Use getattr so programmatic callers that build a Namespace without this
    # field (e.g. scripts/export_resume_documents.py) still work — the default
    # matches the CLI default (private projects suppressed).
    include_private_projects = getattr(args, "include_private_projects", False)
    if (
        resume.independent_projects_visibility == "private"
        and not include_private_projects
    ):
        resume = dc_replace(resume, independent_projects=())

    # Snapshot the assembled-but-pre-pipeline resume so the decision report can
    # diff it against the final resume (rejected bullets, skill-category moves).
    baseline_resume = resume
    bullet_removal_reasons: dict[str, str] = {}

    if args.processing_mode == "processed":
        resume = transform_for_role(resume)
        resume = trim_for_role(resume)
        resume = enrich_data(resume)
        resume = trim_by_rules(resume, removal_reasons=bullet_removal_reasons)
        resume = _apply_display_experience_selection(resume)
        resume = summarize_for_role(resume)
        resume = select_skills(resume, top_n=_resolve_top_skills_cap(args))
        # Compute the shared fit_assessment once against the pre-pipeline
        # baseline so the LLM scores the full canonical bullet set rather
        # than the post-trim view. Filter to the recency-window experiences
        # first (PR #278 review): out-of-window roles never render, so
        # scoring them inflates the prompt, biases the overall score with
        # content the reader can't see, and increases failure risk on long
        # histories. Both consumers below read the same assessment — but
        # the #272 narrative gate may decide *not* to augment the summary
        # even when an assessment exists (off-mode, score above gate,
        # cover-letter), while #271's compression always wants the per-
        # experience scores when they're available. Pass the precomputed
        # assessment into the resolver explicitly to avoid a redundant
        # compute_fit_assessment call (PR #278 review — the LLMClient
        # cache makes most repeat calls cheap, but exception paths return
        # None and would re-issue a full LLM request on the second lookup).
        fit_baseline = _baseline_resume_for_fit_assessment(baseline_resume)
        # Skip the LLM round-trip entirely when no consumer downstream will
        # read the result (e.g. --fit-narrative off + --experience-mode all,
        # or --fit-narrative auto + --cover-letter + --experience-mode all).
        # PR #278 review: avoids latency/cost when neither stage uses scores.
        if _fit_assessment_will_be_consumed(args):
            fit_assessment = compute_fit_assessment(fit_baseline)
        else:
            logger.info(
                "fit_assessment skipped: no downstream consumer "
                "(--fit-narrative=%s, --experience-mode=%s, --cover-letter=%s)",
                getattr(args, "fit_narrative", "auto"),
                getattr(args, "experience_mode", _EXPERIENCE_MODE_AUTO),
                bool(getattr(args, "cover_letter", False)),
            )
            fit_assessment = None
        fit_for_summary = _resolve_fit_narrative(
            args, fit_baseline, fit_assessment=fit_assessment
        )
        resume = summarize_profile_for_role(resume, fit_assessment=fit_for_summary)
        # Mark low-fit experiences as compressed (#271) — render-level switch
        # only; chronology is preserved. Runs after summary so any
        # downstream stages see the experience.compression markers, not
        # because the layout estimator measures the rendered summary text:
        # _compute_bullet_line_budget reserves PROFILE_SUMMARY_MAX_LINES
        # and _SKILLS_TARGET_LINES_MAX as upper bounds regardless of the
        # actual generated content. Pass the underlying assessment (not
        # fit_for_summary) so compression sees per-experience scores even
        # when the narrative gate skipped firing.
        resume = apply_experience_compression(
            args, resume, fit_assessment=fit_assessment
        )

    resume_dir = args.output_dir / RESUME_OUTPUT_SUBDIR
    resume_dir.mkdir(parents=True, exist_ok=True)

    output_prefix = _build_artifact_prefix(processing_mode=args.processing_mode)
    # For processed mode, use modern template as primary; for raw, use default.
    primary_template = "modern" if args.processing_mode == "processed" else "default"
    secondary_template = args.template
    if secondary_template == primary_template:
        secondary_template = "default" if primary_template == "modern" else "modern"

    html_output = resume_dir / f"{output_prefix}.html"
    secondary_html_output = (
        resume_dir
        / f"{_secondary_template_prefix(output_prefix, secondary_template)}.html"
    )
    md_output = resume_dir / f"{output_prefix}.md"
    ir_output = resume_dir / f"{output_prefix}_ir_snapshot.json"
    text_snapshot_output = resume_dir / f"{output_prefix}_ir_snapshot.txt"
    gap_output = resume_dir / f"{output_prefix}_gap_summary.json"
    decision_report_output = resume_dir / f"{output_prefix}_decision_report.json"

    outputs = _resolve_outputs(args)
    needs_html = "html" in outputs
    needs_md = "md" in outputs
    needs_docx = "docx" in outputs
    needs_pdf = "pdf" in outputs

    # Default-template (left-justified) HTML is the preferred DOCX/PDF render
    # source for layout fidelity; markdown is rendered only when explicitly
    # requested or when no default-template HTML will be available
    # (`document_export.iter_markdown_blocks` consumes HTML directly, so MD is
    # not needed alongside HTML for DOCX/PDF rendering).
    has_default_template_html = (
        primary_template == "default" or secondary_template == "default"
    )
    needs_html_render_source = needs_docx or needs_pdf
    needs_md_render_source = (needs_docx or needs_pdf) and not has_default_template_html

    written_paths: list[Path] = []

    # Always emit IR snapshots (debug artifacts, preserved across modes).
    write_ir_snapshot(resume, ir_output)
    write_text_snapshot(resume, text_snapshot_output)
    written_paths.extend([ir_output, text_snapshot_output])

    if needs_html or needs_html_render_source:
        render_html(resume, html_output, template_name=primary_template)
        render_html(resume, secondary_html_output, template_name=secondary_template)
        if needs_html:
            written_paths.extend([html_output, secondary_html_output])
    if needs_md or needs_md_render_source:
        render_markdown(resume, md_output)
        if needs_md:
            written_paths.append(md_output)

    should_emit_gap_summary = (
        args.processing_mode == "processed"
        and resume.job_context is not None
        and bool(resume.job_context.description_excerpt.strip())
    )
    if should_emit_gap_summary:
        write_gap_summary(resume, gap_output)
        written_paths.append(gap_output)

    # Decision report gate is intentionally looser than gap summary: trim_by_rules
    # populates removal reasons and select_skills mutates categories whenever
    # processed-mode runs, regardless of whether a JD is attached or its excerpt
    # is non-empty. The jd_coverage section degrades to zero terms when no JD is
    # present, but the bullet/skill sections remain meaningful.
    if args.processing_mode == "processed":
        write_decision_report(
            resume,
            baseline_resume,
            removal_reasons=bullet_removal_reasons,
            output_path=decision_report_output,
            processing_mode=args.processing_mode,
        )
        written_paths.append(decision_report_output)

    if primary_template == "default":
        default_template_html: Path | None = html_output
    elif secondary_template == "default":
        default_template_html = secondary_html_output
    else:
        default_template_html = None

    docx_output: Path | None = None
    pdf_output: Path | None = None
    removed_legacy_outputs: list[Path] = []
    if needs_docx or needs_pdf:
        docx_output, pdf_output, removed_legacy_outputs = _render_docx_pdf_outputs(
            args=args,
            output_dir=resume_dir,
            html_render_source=default_template_html,
            md_render_source=md_output
            if (needs_md or needs_md_render_source)
            else None,
            emit_docx=needs_docx,
            emit_pdf=needs_pdf,
        )
        if docx_output is not None:
            written_paths.append(docx_output)
        if pdf_output is not None:
            written_paths.append(pdf_output)

    # If HTML/MD were rendered solely as a render source for DOCX/PDF and the
    # user did not request them, remove the staging copies so the on-disk output
    # set matches --outputs exactly.
    if needs_html_render_source and not needs_html:
        html_output.unlink(missing_ok=True)
        secondary_html_output.unlink(missing_ok=True)
    if needs_md_render_source and not needs_md:
        md_output.unlink(missing_ok=True)

    if getattr(args, "cover_letter", False):
        cover_letter_dir = args.output_dir / COVER_LETTER_OUTPUT_SUBDIR
        cover_letter_paths = generate_cover_letter(
            args=args,
            output_dir=cover_letter_dir,
            company=args.company,
            role=resolved_target_role,
        )
        written_paths.extend(cover_letter_paths)
        print(f"Cover letter written to: {cover_letter_dir}")

    print(f"Resume output written to ({args.processing_mode} mode): {resume_dir}")
    for path in written_paths:
        print(f"- {path}")
    if removed_legacy_outputs:
        print("- removed stale legacy exports:")
        for removed_path in removed_legacy_outputs:
            print(f"    {removed_path}")

    return 0


def _resolve_outputs(args: argparse.Namespace) -> tuple[str, ...]:
    """Return validated outputs tokens, defaulting if absent (programmatic callers)."""
    raw = getattr(args, "outputs", DEFAULT_OUTPUTS)
    if raw is None:
        return DEFAULT_OUTPUTS
    if isinstance(raw, str):
        return _parse_outputs(raw)
    tokens = tuple(raw)
    invalid = [t for t in tokens if t not in VALID_OUTPUT_TOKENS]
    if invalid:
        raise ValueError(
            f"--outputs received unknown token(s) {', '.join(invalid)}; "
            f"valid tokens: {', '.join(VALID_OUTPUT_TOKENS)}"
        )
    return tokens


def _render_docx_pdf_outputs(
    *,
    args: argparse.Namespace,
    output_dir: Path,
    html_render_source: Path | None,
    md_render_source: Path | None,
    emit_docx: bool,
    emit_pdf: bool,
) -> tuple[Path | None, Path | None, list[Path]]:
    """Apply post-layout cleanup, then render DOCX/PDF with atomic staging/backup."""
    if html_render_source is not None and html_render_source.exists():
        render_source_text = html_render_source.read_text(encoding="utf-8")
    elif md_render_source is not None and md_render_source.exists():
        render_source_text = md_render_source.read_text(encoding="utf-8")
    else:
        raise RuntimeError(
            "DOCX/PDF render requested but no HTML or markdown source is available."
        )

    post_layout_cleanup = getattr(args, "post_layout_cleanup", "enabled")
    if post_layout_cleanup == "enabled":
        render_source_text = document_export.apply_post_layout_cleanup(
            render_source_text, args=args
        )
    if document_export.contains_trailing_connector_fragment(render_source_text):
        print(
            "WARNING: render source contains trailing connector fragments; "
            "review final DOCX/PDF for awkward wraps",
            file=sys.stderr,
        )

    company = getattr(args, "company", "company")
    pdf_filename = getattr(args, "pdf_filename", None)
    docx_filename = getattr(args, "docx_filename", None)
    allow_overflow_pdf = getattr(args, "allow_overflow_pdf", False)

    docx_output = (
        document_export.resolve_export_output_path(
            output_dir,
            filename_override=docx_filename,
            default_name=document_export.canonical_export_filename(company, "docx"),
            flag_name="--docx-filename",
        )
        if emit_docx
        else None
    )
    pdf_output = (
        document_export.resolve_export_output_path(
            output_dir,
            filename_override=pdf_filename,
            default_name=document_export.canonical_export_filename(company, "pdf"),
            flag_name="--pdf-filename",
        )
        if emit_pdf
        else None
    )

    if (
        docx_output is not None
        and pdf_output is not None
        and docx_output.resolve(strict=False) == pdf_output.resolve(strict=False)
    ):
        raise RuntimeError(
            "DOCX and PDF outputs must be different files; "
            "choose distinct --docx-filename and --pdf-filename values."
        )

    staged_docx = (
        document_export.staging_path(docx_output, label="docx")
        if docx_output is not None
        else None
    )
    staged_pdf = (
        document_export.staging_path(pdf_output, label="pdf")
        if pdf_output is not None
        else None
    )
    backup_docx = (
        document_export.staging_path(docx_output, label="docx.bak")
        if docx_output is not None
        else None
    )
    backup_pdf = (
        document_export.staging_path(pdf_output, label="pdf.bak")
        if pdf_output is not None
        else None
    )
    docx_existed = docx_output.exists() if docx_output is not None else False
    pdf_existed = pdf_output.exists() if pdf_output is not None else False

    if docx_output is not None:
        docx_output.parent.mkdir(parents=True, exist_ok=True)
    if pdf_output is not None:
        pdf_output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if staged_docx is not None:
            document_export.render_docx(render_source_text, staged_docx)
        if staged_pdf is not None:
            document_export.render_pdf(
                render_source_text,
                staged_pdf,
                enforce_page_limit=not allow_overflow_pdf,
            )

        if docx_existed and docx_output is not None and backup_docx is not None:
            docx_output.replace(backup_docx)
        if pdf_existed and pdf_output is not None and backup_pdf is not None:
            pdf_output.replace(backup_pdf)

        if staged_docx is not None and docx_output is not None:
            staged_docx.replace(docx_output)
        if staged_pdf is not None and pdf_output is not None:
            staged_pdf.replace(pdf_output)
    except Exception:
        if staged_docx is not None:
            staged_docx.unlink(missing_ok=True)
        if staged_pdf is not None:
            staged_pdf.unlink(missing_ok=True)
        if backup_docx is not None and backup_docx.exists() and docx_output is not None:
            backup_docx.replace(docx_output)
        elif not docx_existed and docx_output is not None:
            docx_output.unlink(missing_ok=True)
        if backup_pdf is not None and backup_pdf.exists() and pdf_output is not None:
            backup_pdf.replace(pdf_output)
        elif not pdf_existed and pdf_output is not None:
            pdf_output.unlink(missing_ok=True)
        raise

    for backup in (backup_docx, backup_pdf):
        if backup is None:
            continue
        try:
            backup.unlink(missing_ok=True)
        except OSError as _e:
            print(
                f"WARNING: could not remove backup file {backup}: {_e}",
                file=sys.stderr,
            )

    keep: set[Path] = set()
    if docx_output is not None:
        keep.add(docx_output)
    if pdf_output is not None:
        keep.add(pdf_output)
    removed_legacy_outputs = document_export.remove_stale_legacy_exports(
        output_dir.resolve(strict=False), keep
    )
    # Migration: pre-split runs wrote legacy aliases directly to the application
    # root. Sweep that location too so leftover state from earlier runs does not
    # quietly persist after the layout change. Cheap, idempotent, no-op when the
    # files are absent.
    application_root = getattr(args, "output_dir", None)
    if application_root is not None and application_root != output_dir:
        removed_legacy_outputs.extend(
            document_export.remove_stale_legacy_exports(
                Path(application_root).resolve(strict=False), keep
            )
        )
    return docx_output, pdf_output, removed_legacy_outputs


def main() -> int:
    args = parse_args()
    try:
        return run_pipeline(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
