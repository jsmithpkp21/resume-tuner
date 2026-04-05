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
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input


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
    experiences: tuple[Experience, ...]
    skills_by_category: dict[str, list[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--experience-db", type=Path, default=DEFAULT_EXPERIENCE_DB)
    parser.add_argument("--skills-matrix", type=Path, default=DEFAULT_SKILLS_MATRIX)
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
    data = _read_toml(path).get("profile", {})
    if not isinstance(data, dict):
        raise ValueError("profile.toml must contain a [profile] table")

    return Profile(
        name=str(data.get("name", "")),
        headline=str(data.get("headline", "")),
        location=str(data.get("location", "")),
        email=str(data.get("email", "")),
        phone=str(data.get("phone", "")),
        website=str(data.get("website", "")),
        linkedin=str(data.get("linkedin", "")),
        github=str(data.get("github", "")),
        summary=str(data.get("summary", "")),
    )


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

        bullets: list[Bullet] = []
        for raw_bullet in raw_bullets:
            if not isinstance(raw_bullet, dict):
                raise ValueError("Each bullet_bank entry must be a table")
            bullets.append(
                Bullet(
                    id=str(raw_bullet.get("id", "")),
                    text=str(raw_bullet.get("text", "")),
                    skills=tuple(str(skill) for skill in raw_bullet.get("skills", [])),
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
                related_skills=tuple(
                    str(skill) for skill in item.get("related_skills", [])
                ),
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
    experiences: tuple[Experience, ...],
    skills_by_category: dict[str, list[str]],
) -> ResumeIR:
    """Assemble baseline IR with unchanged canonical content."""
    return ResumeIR(
        profile=profile,
        target_role=target_role,
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


def _render_contact(profile: Profile) -> str:
    items = [
        profile.location,
        profile.email,
        profile.phone,
        profile.website,
        profile.linkedin,
        profile.github,
    ]
    filtered = [item for item in items if item.strip()]
    return " | ".join(_html_escape(item) for item in filtered)


def render_html(resume: ResumeIR, output_path: Path) -> None:
    contact_line = _render_contact(resume.profile)
    target_role_line = (
        f'<p class="target-role">Target role: {_html_escape(resume.target_role)}</p>'
        if resume.target_role.strip()
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
                "  </style>",
                "</head>",
                "<body>",
                f"  <h1>{_html_escape(resume.profile.name)}</h1>",
                f'  <p class="headline">{_html_escape(resume.profile.headline)}</p>',
                f'  <p class="contact">{contact_line}</p>',
                f"  {target_role_line}",
                "  <h2>Summary</h2>",
                f"  <p>{_html_escape(resume.profile.summary)}</p>",
                "  <h2>Experience</h2>",
                *experiences_html,
                "  <h2>Skills</h2>",
                *skills_html,
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
        resume.profile.headline,
        "",
        _render_contact(resume.profile),
        "",
    ]

    if resume.target_role.strip():
        lines.extend([f"Target role: {resume.target_role}", ""])

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

    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def write_ir_snapshot(resume: ResumeIR, output_path: Path) -> None:
    payload: dict[str, Any] = {
        "target_role": resume.target_role,
        "profile": {
            "name": resume.profile.name,
            "headline": resume.profile.headline,
            "location": resume.profile.location,
            "email": resume.profile.email,
            "phone": resume.profile.phone,
            "website": resume.profile.website,
            "linkedin": resume.profile.linkedin,
            "github": resume.profile.github,
            "summary": resume.profile.summary,
        },
        "experience_count": len(resume.experiences),
        "bullet_count": sum(len(exp.bullets) for exp in resume.experiences),
        "skills_category_count": len(resume.skills_by_category),
        "skills_count": sum(
            len(skills) for skills in resume.skills_by_category.values()
        ),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run_pipeline(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    experiences = load_experiences(args.experience_db)
    skills_by_category = load_skills_by_category(args.skills_matrix)

    resume = assemble_baseline_resume(
        profile=profile,
        target_role=args.target_role,
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
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
