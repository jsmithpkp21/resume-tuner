#!/usr/bin/env python3
"""Build a baseline resume artifact from canonical data.

Milestone-1 behavior intentionally favors output speed and manual finishability:
- include all canonical experiences and bullets
- preserve canonical bullet text unchanged
- keep transform/trim stages as explicit no-op hooks for future phases
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

# Use local import when run as `python scripts/build_resume.py`,
# and package import when loaded as `scripts.build_resume`.
if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
    from jd_ingest import JobContext, ingest_job_context, ingest_job_text
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input
    from scripts.jd_ingest import JobContext, ingest_job_context, ingest_job_text


DEFAULT_PROFILE = Path("data/profile/profile.toml")
DEFAULT_EXPERIENCE_DB = Path("data/experience/experience_db.toml")
DEFAULT_SKILLS_MATRIX = Path("data/skills/skills_matrix.csv")
DEFAULT_OUTPUT_DIR = Path("data/review/outputs/baseline")


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
        "--skip-markdown",
        action="store_true",
        help="Write only HTML and JSON artifacts.",
    )
    return parser.parse_args()


def _read_toml(path: Path) -> dict[str, Any]:
    assert_not_blocked_runtime_input(path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_profile(path: Path) -> Profile:
    payload = _read_toml(path)
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


def _normalize_linkedin_slug(value: str) -> str:
    """Accept slug or URL-like input, then keep only the LinkedIn /in/ slug."""
    cleaned = value.strip().replace("http://", "").replace("https://", "")
    cleaned = cleaned.replace("www.", "")
    cleaned = cleaned.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if cleaned.startswith("linkedin.com/in/"):
        cleaned = cleaned[len("linkedin.com/in/") :]
    elif cleaned.startswith("in/"):
        cleaned = cleaned[len("in/") :]
    cleaned = cleaned.strip().strip("/")
    return cleaned.split("/", maxsplit=1)[0].strip()


def _normalize_github_username(value: str) -> str:
    """Accept username or URL-like input, then keep only the GitHub username."""
    cleaned = value.strip().replace("http://", "").replace("https://", "")
    cleaned = cleaned.replace("www.", "")
    cleaned = cleaned.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    if cleaned.startswith("github.com/"):
        cleaned = cleaned[len("github.com/") :]
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
    """Use target role as headline when provided, else keep profile headline."""
    dynamic = target_role.strip()
    if dynamic:
        return dynamic
    return profile.headline


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
    )


def transform_for_role(resume: ResumeIR) -> ResumeIR:
    """No-op placeholder for future role-specific rewriting stage."""
    return resume


def trim_for_role(resume: ResumeIR) -> ResumeIR:
    """No-op placeholder for future role-relevance trimming stage."""
    return resume


def enrich_data(resume: ResumeIR) -> ResumeIR:
    """No-op placeholder for future data enrichment stage."""
    return resume


def trim_by_rules(resume: ResumeIR) -> ResumeIR:
    """No-op placeholder for future layout/rules trimming stage."""
    return resume


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
    items = [
        profile.location,
        profile.email,
        profile.phone,
        profile.website,
        _build_linkedin_url(profile.linkedin),
        _build_github_url(profile.github),
    ]
    return " | ".join(item for item in items if item.strip())


def render_html(resume: ResumeIR, output_path: Path) -> None:
    contact_line = _render_contact_html(resume.profile)
    target_role_line = (
        f'<p class="target-role">Target role: {_html_escape(resume.target_role)}</p>'
        if resume.target_role.strip()
        else ""
    )
    target_company_line = (
        f'<p class="target-role">Target company: {_html_escape(resume.target_company)}</p>'
        if resume.target_company.strip()
        else ""
    )

    experiences_html: list[str] = []
    for exp in resume.experiences:
        bullets_html = "\n".join(
            f"<li>{_html_escape(bullet.text)}</li>" for bullet in exp.bullets
        )
        related = ", ".join(_html_escape(skill) for skill in exp.related_skills)
        related_html = (
            f'<p class="related-skills"><strong>Related skills:</strong> {related}</p>'
            if related
            else ""
        )
        experiences_html.append(
            "\n".join(
                [
                    '<section class="experience-item">',
                    (
                        f"<h3>{_html_escape(exp.job_title)}"
                        f"<span> | {_html_escape(exp.company)}</span></h3>"
                    ),
                    (
                        f'<p class="dates">{_html_escape(exp.start_date)}'
                        f" - {_html_escape(exp.end_date)}</p>"
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
        )

    skills_html: list[str] = []
    for category, skills in resume.skills_by_category.items():
        joined_skills = ", ".join(_html_escape(skill) for skill in skills)
        skills_html.append(
            f"<p><strong>{_html_escape(category)}:</strong> {joined_skills}</p>"
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

    output_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8" />',
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
                f"  <title>{_html_escape(resume.profile.name)} - Resume</title>",
                "  <style>",
                "    body { font-family: Arial, sans-serif; margin: 24px auto; max-width: 960px; line-height: 1.4; }",
                "    h1 { margin-bottom: 4px; }",
                "    h2 { border-bottom: 1px solid #ccc; margin-top: 20px; padding-bottom: 4px; }",
                "    h3 { margin-bottom: 2px; }",
                "    h3 span { font-weight: normal; color: #333; }",
                "    .headline, .contact, .target-role, .dates, .role-summary, .related-skills { margin: 4px 0; }",
                "    ul { margin-top: 6px; }",
                "    .experience-item { margin-bottom: 16px; }",
                "    .info-item { margin-bottom: 10px; }",
                "  </style>",
                "</head>",
                "<body>",
                f"  <h1>{_html_escape(resume.profile.name)}</h1>",
                f'  <p class="headline">{_html_escape(resume.display_headline)}</p>',
                f'  <p class="contact">{contact_line}</p>',
                f"  {target_role_line}",
                f"  {target_company_line}",
                "  <h2>Summary</h2>",
                f"  <p>{_html_escape(resume.profile.summary)}</p>",
                "  <h2>Experience</h2>",
                *experiences_html,
                "  <h2>Skills</h2>",
                *skills_html,
                "  <h2>Education</h2>" if education_html else "",
                *education_html,
                "  <h2>Leadership &amp; Community</h2>" if leadership_html else "",
                *leadership_html,
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )


def render_markdown(resume: ResumeIR, output_path: Path) -> None:
    lines: list[str] = [
        f"# {resume.profile.name}",
        "",
        resume.display_headline,
        "",
        _render_contact_markdown(resume.profile),
        "",
    ]

    if resume.target_role.strip():
        lines.extend([f"Target role: {resume.target_role}", ""])
    if resume.target_company.strip():
        lines.extend([f"Target company: {resume.target_company}", ""])

    lines.extend(["## Summary", "", resume.profile.summary, "", "## Experience", ""])

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

    lines.extend(["## Skills", ""])
    for category, skills in resume.skills_by_category.items():
        lines.append(f"- **{category}:** {', '.join(skills)}")

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
    }
    if resume.job_context is not None:
        payload["job_context"] = resume.job_context.to_dict()
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_pipeline(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    experiences = load_experiences(args.experience_db)
    skills_by_category = load_skills_by_category(args.skills_matrix)
    has_job_url = args.job_url.strip() != ""
    has_job_text_file = args.job_text_file is not None
    if has_job_url and has_job_text_file:
        raise ValueError("Provide only one of --job-url or --job-text-file")

    job_context: JobContext | None = None
    if has_job_text_file:
        assert_not_blocked_runtime_input(args.job_text_file)
        job_text = args.job_text_file.read_text(encoding="utf-8")
        job_context = ingest_job_text(job_text, source_hint="job-text-file")
    elif has_job_url:
        job_context = ingest_job_context(args.job_url)

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
    )
    resume = transform_for_role(resume)
    resume = trim_for_role(resume)
    resume = enrich_data(resume)
    resume = trim_by_rules(resume)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    html_output = args.output_dir / "resume_baseline.html"
    md_output = args.output_dir / "resume_baseline.md"
    ir_output = args.output_dir / "resume_ir_snapshot.json"

    render_html(resume, html_output)
    if not args.skip_markdown:
        render_markdown(resume, md_output)
    write_ir_snapshot(resume, ir_output)

    print(f"Baseline resume output written to: {args.output_dir}")
    print(f"- {html_output}")
    if not args.skip_markdown:
        print(f"- {md_output}")
    print(f"- {ir_output}")
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
