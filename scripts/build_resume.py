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
from collections.abc import Sequence
from dataclasses import dataclass, field
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from resume_templates import TemplateContext, get_template
    from select_skills import join_skills, select_skills
else:
    from scripts.resume_templates import TemplateContext, get_template
    from scripts.select_skills import join_skills, select_skills

# Use local import when run as `python scripts/build_resume.py`,
# and package import when loaded as `scripts.build_resume`.
if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
    from jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from llm_client import LLMClient
    from measurable_outcomes import (
        has_measurable_outcome as _shared_has_measurable_outcome,
    )
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input
    from scripts.jd_ingest import JobContext, ingest_job_context, ingest_job_text
    from scripts.llm_client import LLMClient
    from scripts.measurable_outcomes import (
        has_measurable_outcome as _shared_has_measurable_outcome,
    )


DEFAULT_PROFILE = Path("data/profile/profile.toml")
LOCAL_PROFILE_SUFFIX = ".local.toml"
DEFAULT_EXPERIENCE_DB = Path("data/experience/experience_db.toml")
DEFAULT_SKILLS_MATRIX = Path("data/skills/skills_matrix.csv")
DEFAULT_OUTPUT_DIR = Path("data/review/outputs/baseline")
# Role-level selection should not hard-cap bullets; keep all and rank by relevance.
# Final output fitting is enforced by a line-budget pass.
DEFAULT_BULLET_LINE_WIDTH = 108
DEFAULT_MAX_BULLET_LINES = 52
# Calibrated two-page line budget for pre-render trimming.
# This value intentionally keeps processed output near full two-page utilization
# under the current template while allowing dynamic reductions on high-pressure
# layouts.
DEFAULT_TOTAL_PAGE_LINES = 160
DEFAULT_MAX_ACTION_WORD_OCCURRENCES = 2
DEFAULT_MIN_BULLETS_PER_EXPERIENCE = 2
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
LLM_ENABLED_ENV = "RESUME_BUILDER_LLM_ENABLED"
LLM_FIXTURE_ENV = "RESUME_BUILDER_LLM_FIXTURE"

_LOCAL_PROFILE_OVERRIDE_FIELDS = {
    "name",
    "headline",
    "location",
    "email",
    "phone",
    "website",
    "linkedin",
    "github",
}

_LOCAL_PROFILE_SECTION_OVERRIDE_FIELDS = {
    "education",
    "leadership_community",
}


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
class Bullet:
    id: str
    text: str
    skills: tuple[str, ...]
    impact_type: str
    domain: str


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--experience-db", type=Path, default=DEFAULT_EXPERIENCE_DB)
    parser.add_argument("--skills-matrix", type=Path, default=DEFAULT_SKILLS_MATRIX)
    parser.add_argument("--job-url", type=str, default="")
    parser.add_argument(
        "--job-text-file",
        type=Path,
        default=None,
        help="Path to a plain-text file containing the full job description.",
    )
    parser.add_argument("--target-role", type=str, default="")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--processing-mode",
        choices=("raw", "processed"),
        default="raw",
        help=(
            "raw keeps canonical content unfiltered (baseline contract); "
            "processed runs transform/trim/enrich/rule/select stages."
        ),
    )
    parser.add_argument(
        "--skip-markdown",
        action="store_true",
        help="Skip Markdown output; HTML plus JSON/text IR snapshots are still written.",
    )
    parser.add_argument(
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
    return parser.parse_args()


def _read_toml(path: Path) -> dict[str, Any]:
    assert_not_blocked_runtime_input(path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_profile(path: Path) -> Profile:
    payload = _read_toml(path)
    payload = _merge_profile_local_override(path, payload)
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
    )


def _profile_local_override_path(path: Path) -> Path:
    if path.name.endswith(".toml"):
        return path.with_name(path.name[: -len(".toml")] + LOCAL_PROFILE_SUFFIX)
    return path.with_name(path.name + LOCAL_PROFILE_SUFFIX)


def _merge_profile_local_override(
    path: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    if path.name.endswith(LOCAL_PROFILE_SUFFIX):
        raise ValueError(
            f"{path.name} is already a local override file; pass the tracked base profile .toml path"
        )

    local_path = _profile_local_override_path(path)
    if local_path.exists() and not local_path.is_file():
        raise ValueError(f"{local_path.name} must be a regular file")
    if not local_path.exists():
        return payload

    local_payload = _read_toml(local_path)
    local_profile = local_payload.get("profile", {})
    if not isinstance(local_profile, dict):
        raise ValueError(f"{local_path.name} must contain a [profile] table")

    base_profile = payload.get("profile", {})
    if not isinstance(base_profile, dict):
        raise ValueError(f"{path.name} must contain a [profile] table")

    merged_payload = dict(payload)
    merged_profile = dict(base_profile)
    for field_name in _LOCAL_PROFILE_OVERRIDE_FIELDS:
        if field_name in local_profile:
            merged_profile[field_name] = local_profile[field_name]
    merged_payload["profile"] = merged_profile

    for section_name in _LOCAL_PROFILE_SECTION_OVERRIDE_FIELDS:
        if section_name not in local_payload:
            continue
        section_data = local_payload[section_name]
        if not isinstance(section_data, list):
            raise ValueError(
                f"{local_path.name} {section_name} must use [[{section_name}]] entries"
            )
        if any(not isinstance(item, dict) for item in section_data):
            raise ValueError(f"{local_path.name} {section_name} entries must be tables")
        merged_payload[section_name] = section_data

    return merged_payload


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
                )
            )

        experiences.append(
            Experience(
                id=str(item.get("id", "")),
                job_title=str(item.get("job_title", "")),
                company=str(item.get("company", "")),
                start_date=str(item.get("start_date", "")),
                end_date=str(item.get("end_date", "")),
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


def write_gap_summary(resume: ResumeIR, output_path: Path) -> None:
    """Write missing high-value JD terms not yet covered by selected skills/bullets."""
    description_excerpt = ""
    role_hint = ""
    if resume.job_context is not None:
        description_excerpt = resume.job_context.description_excerpt.strip()
        role_hint = resume.job_context.role_hint.strip()

    job_terms = _tokenize_gap_terms(
        " ".join(
            part
            for part in [
                description_excerpt,
                role_hint,
            ]
            if part.strip()
        )
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
        "job_term_count": len(job_terms),
        "unique_job_terms": len(job_term_counts),
        "covered_term_count": sum(
            1 for term in job_term_counts if term in covered_terms
        ),
        "missing_terms": missing_terms,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


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
    )


def _llm_stage_enabled() -> bool:
    llm_enabled = os.getenv(LLM_ENABLED_ENV, "0").strip() == "1"
    fixture_enabled = os.getenv(LLM_FIXTURE_ENV, "0").strip() == "1"
    return llm_enabled or fixture_enabled


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


def trim_by_rules(resume: ResumeIR) -> ResumeIR:
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


def summarize_profile_for_role(resume: ResumeIR) -> ResumeIR:
    """Generate a concise top-of-page summary from processed resume content."""
    generated_summary = _generate_profile_summary(resume)
    if not generated_summary or generated_summary == resume.profile.summary:
        return resume

    updated_profile = dc_replace(resume.profile, summary=generated_summary)
    return dc_replace(resume, profile=updated_profile)


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
) -> tuple[Experience, ...]:
    selected_by_experience = [list(experience.bullets) for experience in experiences]

    _drop_duplicate_bullets(selected_by_experience)
    _limit_action_word_repetition(
        selected_by_experience,
        enrichment_by_bullet_id=enrichment_by_bullet_id,
    )
    _enforce_bullet_line_budget(
        selected_by_experience,
        enrichment_by_bullet_id=enrichment_by_bullet_id,
        max_bullet_lines=max_bullet_lines,
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


def _drop_duplicate_bullets(selected_by_experience: list[list[Bullet]]) -> None:
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
                continue
            filtered.append(bullet)
            seen_texts.add(normalized_text)
        bullets[:] = filtered


def _limit_action_word_repetition(
    selected_by_experience: list[list[Bullet]],
    *,
    enrichment_by_bullet_id: dict[str, dict[str, object]],
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
            selected_by_experience[exp_index] = [
                existing for existing in current if existing.id != bullet.id
            ]


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

    This budget is a ceiling, not a fill target; downstream selection never adds
    bullets solely because budget remains.
    """
    # Header block: name + display headline + contact + divider/title spacing.
    header_lines = 4
    title_line = 1
    summary_lines = _estimate_wrapped_line_count(
        resume.profile.summary,
        PROFILE_SUMMARY_LINE_WIDTH,
    )
    section_header_lines = 1  # Key Skills
    section_header_lines += 1  # Professional Experience
    if resume.cross_org_architectural_leadership:
        section_header_lines += 1
    if resume.selected_achievements:
        section_header_lines += 1
    if resume.profile.education_entries:
        section_header_lines += 1
    if resume.profile.leadership_community_entries:
        section_header_lines += 1

    skills_lines = sum(
        _estimate_wrapped_line_count(
            f"{category}: {join_skills(skills)}",
            DEFAULT_BULLET_LINE_WIDTH,
        )
        for category, skills in resume.skills_by_category.items()
    )

    cross_org_lines = sum(
        _estimate_wrapped_line_count(item.text, DEFAULT_BULLET_LINE_WIDTH)
        for item in resume.cross_org_architectural_leadership
    )
    selected_achievement_lines = sum(
        _estimate_wrapped_line_count(item.text, DEFAULT_BULLET_LINE_WIDTH)
        for item in resume.selected_achievements
    )

    role_header_lines = 0
    company_blocks = _company_block_ranges(resume.experiences)

    for exp_index, experience in enumerate(resume.experiences):
        if exp_index in company_blocks:
            role_header_lines += 1  # grouped company-line header
        role_header_lines += 1  # job-title-line already includes date range
        role_header_lines += _estimate_wrapped_line_count(
            experience.general_role_description,
            SUMMARY_LINE_WIDTH,
        )

    education_lines = 0
    for education_item in resume.profile.education_entries:
        education_lines += 1
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
            education_lines += _estimate_wrapped_line_count(
                metadata,
                DEFAULT_BULLET_LINE_WIDTH,
            )
        if education_item.notes.strip():
            education_lines += _estimate_wrapped_line_count(
                education_item.notes,
                DEFAULT_BULLET_LINE_WIDTH,
            )

    leadership_lines = 0
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
            leadership_lines += _estimate_wrapped_line_count(
                header,
                DEFAULT_BULLET_LINE_WIDTH,
            )
        if leadership_item.details.strip():
            leadership_lines += _estimate_wrapped_line_count(
                leadership_item.details,
                DEFAULT_BULLET_LINE_WIDTH,
            )

    non_bullet_lines = (
        header_lines
        + title_line
        + summary_lines
        + section_header_lines
        + skills_lines
        + cross_org_lines
        + selected_achievement_lines
        + role_header_lines
        + education_lines
        + leadership_lines
    )

    minimum_floor_lines = _estimate_minimum_required_bullet_lines(resume.experiences)
    computed_budget = max(
        minimum_floor_lines, DEFAULT_TOTAL_PAGE_LINES - non_bullet_lines
    )

    # Keep the historical constant as a deterministic safety cap. This allows
    # tests/config to force an intentionally strict cap and verify floor warnings.
    capped_budget = max(1, min(DEFAULT_MAX_BULLET_LINES, computed_budget))
    logger.debug(
        "Computed bullet-line budget=%s (non_bullet_lines=%s, floor=%s)",
        capped_budget,
        non_bullet_lines,
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


def _date_sort_key(raw: str, *, is_end: bool) -> tuple[int, int]:
    """Sort key for yyyy-mm dates, treating 'Present' as far-future for end dates."""
    value = raw.strip().lower()
    if value in {"present", "current", "now"}:
        return (9999, 12) if is_end else (0, 1)
    match = re.fullmatch(r"(\d{4})-(\d{2})", raw.strip())
    if not match:
        return (0, 1)
    return (int(match.group(1)), int(match.group(2)))


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
        bullets_html = "\n".join(
            f"<li>{_html_escape(bullet.text)}</li>" for bullet in exp.bullets
        )
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
        lines.extend(
            [
                (
                    f'<h3 class="job-title-line">{_html_escape(exp.job_title)}'
                    f"<span>{_html_escape(role_date_range)}</span></h3>"
                ),
                (
                    f'<p class="role-summary">'
                    f"{_html_escape(exp.general_role_description)}</p>"
                ),
                related_html,
                "<ul>",
                bullets_html,
                "</ul>",
                "</section>",
            ]
        )
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

    lines.extend(["", "## Professional Experience", ""])

    for exp in resume.experiences:
        lines.extend(
            [
                f"### {exp.job_title} | {exp.company}",
                f"{exp.start_date} - {exp.end_date}",
                "",
                exp.general_role_description,
                "",
            ]
        )
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
    elif has_job_url:
        job_context = ingest_job_context(job_url)

    resolved_target_role = args.target_role.strip()
    if not resolved_target_role and job_context is not None:
        resolved_target_role = job_context.role_hint

    resolved_target_company = ""
    if job_context is not None:
        resolved_target_company = job_context.company_name

    resume = assemble_baseline_resume(
        profile=profile,
        target_role=resolved_target_role,
        target_company=resolved_target_company,
        job_context=job_context,
        experiences=experiences,
        skills_by_category=skills_by_category,
        cross_org_architectural_leadership=cross_org_architectural_leadership,
        selected_achievements=selected_achievements,
    )
    if args.processing_mode == "processed":
        resume = transform_for_role(resume)
        resume = trim_for_role(resume)
        resume = enrich_data(resume)
        resume = trim_by_rules(resume)
        resume = summarize_for_role(resume)
        resume = select_skills(resume)
        resume = summarize_profile_for_role(resume)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    output_prefix = _build_artifact_prefix(processing_mode=args.processing_mode)
    # For processed mode, use modern template as primary; for raw, use default.
    primary_template = "modern" if args.processing_mode == "processed" else "default"
    secondary_template = args.template
    if secondary_template == primary_template:
        secondary_template = "default" if primary_template == "modern" else "modern"

    html_output = args.output_dir / f"{output_prefix}.html"
    secondary_html_output = (
        args.output_dir
        / f"{_secondary_template_prefix(output_prefix, secondary_template)}.html"
    )
    md_output = args.output_dir / f"{output_prefix}.md"
    ir_output = args.output_dir / f"{output_prefix}_ir_snapshot.json"
    text_snapshot_output = args.output_dir / f"{output_prefix}_ir_snapshot.txt"
    gap_output = args.output_dir / f"{output_prefix}_gap_summary.json"

    render_html(resume, html_output, template_name=primary_template)
    render_html(resume, secondary_html_output, template_name=secondary_template)
    if not args.skip_markdown:
        render_markdown(resume, md_output)
    write_ir_snapshot(resume, ir_output)
    write_text_snapshot(resume, text_snapshot_output)
    should_emit_gap_summary = (
        args.processing_mode == "processed"
        and resume.job_context is not None
        and bool(resume.job_context.description_excerpt.strip())
    )
    if should_emit_gap_summary:
        write_gap_summary(resume, gap_output)

    print(f"Resume output written to ({args.processing_mode} mode): {args.output_dir}")
    print(f"- {html_output}")
    print(f"- {secondary_html_output}")
    if not args.skip_markdown:
        print(f"- {md_output}")
    print(f"- {ir_output}")
    print(f"- {text_snapshot_output}")
    if should_emit_gap_summary:
        print(f"- {gap_output}")
    return 0


def main() -> int:
    args = parse_args()
    try:
        return run_pipeline(args)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
