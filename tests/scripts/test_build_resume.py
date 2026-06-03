from __future__ import annotations

import argparse
import dataclasses
import html as html_lib
import io
import ipaddress
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from http.client import HTTPMessage
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest

from resume_builder import build_resume, jd_ingest
from resume_builder.build_resume import (
    PROFILE_SUMMARY_MAX_LINES,
    PROFILE_SUMMARY_MAX_WORDS,
    PROFILE_SUMMARY_MIN_RATIO,
    Bullet,
    Experience,
    _build_github_url,
    _build_linkedin_url,
    _collect_resume_skill_signals,
    _display_company_header,
    _get_base_role,
    _has_measurable_outcome,
    _summary_wrap_lines,
    assemble_baseline_resume,
    derive_resume_title,
    enrich_data,
    load_experiences,
    load_profile,
    summarize_for_role,
    summarize_profile_for_role,
    transform_for_role,
    trim_by_rules,
    trim_for_role,
)
from resume_builder.jd_ingest import FetchedPage, ingest_job_context
from resume_builder.measure_skills_lines import (
    TARGET_LINES_MAX,
    TARGET_LINES_MIN,
    load_font_pair,
    measure_skills_section,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_resume.py"
# data/profile/profile.toml is per-contributor runtime input (gitignored).
# Tests use a tracked synthetic baseline so behavior is reproducible across machines and CI.
PROFILE = REPO_ROOT / "tests" / "fixtures" / "profile" / "profile_baseline.toml"
SCHWAB_JOB_URL = (
    "https://www.schwabjobs.com/job/austin/"
    "sr-sdet-workplace-services-engineering/33727/92422911552"
)
SCHWAB_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "job_pages" / "schwab_sr_sdet.html"
_TRACKED_PROFILE_TMPDIR = tempfile.TemporaryDirectory(
    prefix="resume-builder-profile-test-"
)
_TRACKED_PROFILE_PATH = Path(_TRACKED_PROFILE_TMPDIR.name) / "profile.toml"
_TRACKED_PROFILE_PATH.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
CURRENT_PROFILE = load_profile(_TRACKED_PROFILE_PATH)
PROFILE_HEADLINE = CURRENT_PROFILE.headline


def _expected_resume_title(profile: build_resume.Profile) -> str:
    return derive_resume_title(
        build_resume.ResumeIR(
            profile=profile,
            target_role="",
            target_company="",
            display_headline="",
            job_context=None,
            experiences=(),
            skills_by_category={},
        )
    )


PROFILE_RESUME_TITLE = _expected_resume_title(CURRENT_PROFILE)
PROFILE_PRIMARY_ROLE = PROFILE_RESUME_TITLE.split(" / ", maxsplit=1)[0]


def _extract_skills_by_category_from_html(html_text: str) -> dict[str, list[str]]:
    """Parse rendered skills paragraphs back into category -> skills lists."""
    skills_by_category: dict[str, list[str]] = {}
    matches = re.findall(
        r'<p class="skills-category"><strong>([^<]+):</strong>\s*(.*?)</p>',
        html_text,
        flags=re.S,
    )
    for category, body in matches:
        clean = re.sub(r"<[^>]+>", "", body)
        skills = [
            html_lib.unescape(skill.strip())
            for skill in clean.split("•")
            if skill.strip()
        ]
        skills_by_category[html_lib.unescape(category)] = skills
    return skills_by_category


def test_load_profile_reads_profile_table(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    profile = load_profile(profile_path)
    assert profile.name
    assert profile.summary
    assert profile.education_entries
    assert profile.leadership_community_entries
    assert profile.github == ""


def test_load_profile_missing_file_points_at_example_template(tmp_path: Path) -> None:
    missing_path = tmp_path / "profile.toml"

    with pytest.raises(ValueError, match="profile.example.toml") as excinfo:
        load_profile(missing_path)

    assert isinstance(excinfo.value.__cause__, FileNotFoundError)


def test_load_profile_normalizes_url_like_social_inputs(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Test"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = "https://www.linkedin.com/in/test-user/detail?trk=foo#top"
github = "https://github.com/test-user/repositories?tab=projects"
summary = ""
""".strip()
        + "\n",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    assert profile.linkedin == "test-user"
    assert profile.github == "test-user"


def test_load_profile_rejects_blocked_path() -> None:
    blocked = REPO_ROOT / "data" / "samples" / "profile.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_profile(blocked)


def test_load_profile_rejects_non_table_education_entry(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
education = "not-a-table"

[profile]
name = "Test"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = "test-user"
github = "test-user"
summary = ""
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="education"):
        load_profile(profile_path)


def test_load_experiences_rejects_string_skills_entries(tmp_path: Path) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Engineer"
company = "Contoso"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = "python"

[[experience.bullet_bank]]
id = "b1"
text = "Built tests"
skills = ["python"]
impact_type = "quality"
domain = "automation"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="related_skills"):
        load_experiences(experience_path)


def test_load_cross_org_architectural_leadership_resolves_source_ids() -> None:
    experience_path = REPO_ROOT / "data" / "experience" / "experience_db.toml"
    experiences = load_experiences(experience_path)

    entries = build_resume.load_cross_org_architectural_leadership(
        experience_path, experiences=experiences
    )

    assert len(entries) >= 3
    assert entries[0].source_bullet_ids
    assert "exp_hp_poly_technical_lead_framework_integration_201906_b03" in {
        source_id for entry in entries for source_id in entry.source_bullet_ids
    }


def test_load_cross_org_architectural_leadership_rejects_unknown_source_ids(
    tmp_path: Path,
) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Engineer"
company = "Contoso"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Built tests"
skills = ["Python"]
impact_type = "quality"
domain = "automation"

[cross_org_architectural_leadership]
title = "Cross-Org Architectural Leadership"

[[cross_org_architectural_leadership.items]]
text = "Cross-org leadership summary"
source_bullet_ids = ["missing-bullet-id"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)
    with pytest.raises(ValueError, match="Unknown cross_org_architectural_leadership"):
        build_resume.load_cross_org_architectural_leadership(
            experience_path,
            experiences=experiences,
        )


def test_load_selected_achievements_resolves_source_ids() -> None:
    experience_path = REPO_ROOT / "data" / "experience" / "experience_db.toml"
    experiences = load_experiences(experience_path)

    entries = build_resume.load_selected_achievements(
        experience_path, experiences=experiences
    )

    assert len(entries) >= 3
    assert entries[0].source_bullet_ids
    assert "exp_hp_poly_technical_lead_framework_integration_201906_b02" in {
        source_id for entry in entries for source_id in entry.source_bullet_ids
    }


def test_load_selected_achievements_rejects_unknown_source_ids(
    tmp_path: Path,
) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Engineer"
company = "Contoso"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Built tests"
skills = ["Python"]
impact_type = "quality"
domain = "automation"

[selected_achievements]
title = "Selected Achievements"

[[selected_achievements.items]]
text = "Key achievement summary"
source_bullet_ids = ["missing-bullet-id"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)
    with pytest.raises(ValueError, match="Unknown selected_achievements"):
        build_resume.load_selected_achievements(
            experience_path,
            experiences=experiences,
        )


def test_load_independent_projects_resolves_source_ids() -> None:
    experience_path = REPO_ROOT / "data" / "experience" / "experience_db.toml"
    experiences = load_experiences(experience_path)

    entries, visibility = build_resume.load_independent_projects(
        experience_path, experiences=experiences
    )

    assert visibility in ("public", "private")
    assert len(entries) >= 3
    assert entries[0].name
    assert entries[0].source_bullet_ids
    all_source_ids = {
        source_id for entry in entries for source_id in entry.source_bullet_ids
    }
    assert "exp_jjs_dev_labs_independent_se_202602_b01" in all_source_ids


def test_load_independent_projects_rejects_unknown_source_ids(
    tmp_path: Path,
) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Engineer"
company = "Contoso"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Built tests"
skills = ["Python"]
impact_type = "quality"
domain = "automation"

[independent_projects]
title = "Independent Projects"
visibility = "public"

[[independent_projects.items]]
name = "Sample Project"
summary = "Summary"
key_skills = ["Python"]
source_bullet_ids = ["missing-bullet-id"]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)
    with pytest.raises(ValueError, match="Unknown independent_projects"):
        build_resume.load_independent_projects(
            experience_path,
            experiences=experiences,
        )


def test_load_independent_projects_rejects_invalid_visibility(tmp_path: Path) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Engineer"
company = "Contoso"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Built tests"
skills = ["Python"]
impact_type = "quality"
domain = "automation"

[independent_projects]
visibility = "internal"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)
    with pytest.raises(ValueError, match="independent_projects.visibility"):
        build_resume.load_independent_projects(
            experience_path,
            experiences=experiences,
        )


def _independent_projects_test_experience_db(*, visibility: str, items: str) -> str:
    return (
        """
[[experience]]
id = "exp-acme"
job_title = "Engineer"
company = "Acme"
start_date = "2021-01"
end_date = "2022-01"
general_role_description = "Did things"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "exp-acme-b1"
text = "Built deterministic CI quality gates."
skills = ["Python", "CI"]
impact_type = "quality"
domain = "automation"

[independent_projects]
title = "Independent Projects"
"""
        + f'visibility = "{visibility}"\n'
        + items
    )


def _run_build_resume_cli(
    *,
    experience_db: Path,
    profile_path: Path,
    output_dir: Path,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--profile",
        str(profile_path),
        "--experience-db",
        str(experience_db),
        "--output-dir",
        str(output_dir),
        "--target-role",
        "Staff Software Engineer",
    ]
    if not any(arg.startswith("--outputs") for arg in extra_args):
        args += ["--outputs", "html,md"]
    if not any(arg.startswith("--processing-mode") for arg in extra_args):
        # Existing tests assert on `latest_resume_raw.*` artifacts; preserve
        # that intent now that the build_resume CLI default is `processed`.
        args += ["--processing-mode", "raw"]
    args += list(extra_args)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_independent_projects_private_skipped_by_default(tmp_path: Path) -> None:
    """Canonical private visibility omits the section unless the flag is set."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
    )
    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert "<h2>Independent Projects</h2>" not in html_text
    assert "## Independent Projects" not in md_text
    assert snapshot["independent_projects_visibility"] == "private"
    # Filter zeroes the rendered list, but visibility is preserved for audit.
    assert int(snapshot["independent_projects_count"]) == 0


def test_independent_projects_included_with_flag(tmp_path: Path) -> None:
    """`--include-private-projects` opts the canonical private section in."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
        extra_args=("--include-private-projects",),
    )
    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert "<h2>Independent Projects</h2>" in html_text
    assert "## Independent Projects" in md_text
    assert "Multi-repo platform" in html_text
    assert "Multi-repo platform" in md_text
    assert int(snapshot["independent_projects_count"]) >= 3
    # Section sits between Selected Achievements and Professional Experience.
    assert html_text.index("<h2>Selected Achievements</h2>") < html_text.index(
        "<h2>Independent Projects</h2>"
    )
    assert html_text.index("<h2>Independent Projects</h2>") < html_text.index(
        "<h2>Professional Experience</h2>"
    )
    assert md_text.index("## Selected Achievements") < md_text.index(
        "## Independent Projects"
    )
    assert md_text.index("## Independent Projects") < md_text.index(
        "## Professional Experience"
    )


def test_independent_projects_public_visibility_renders_without_flag(
    tmp_path: Path,
) -> None:
    items = """
[[independent_projects.items]]
name = "Public Repo Showcase"
summary = "Open-source platform demoing CI quality gates."
key_skills = ["Python", "CI"]
source_bullet_ids = ["exp-acme-b1"]
url = "https://example.com/repo"
"""
    experience_db = tmp_path / "experience_db.toml"
    experience_db.write_text(
        _independent_projects_test_experience_db(visibility="public", items=items),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_build_resume_cli(
        experience_db=experience_db,
        profile_path=profile_path,
        output_dir=output_dir,
    )
    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )

    assert "<h2>Independent Projects</h2>" in html_text
    assert 'href="https://example.com/repo"' in html_text
    assert "Public Repo Showcase" in html_text
    assert "## Independent Projects" in md_text
    assert "[Public Repo Showcase](https://example.com/repo)" in md_text


def test_run_pipeline_tolerates_namespace_without_include_private_projects(
    tmp_path: Path,
) -> None:
    """Programmatic callers (e.g. export_resume_documents) build a Namespace
    by hand. run_pipeline must not raise AttributeError when the field is
    absent — the defensive getattr should fall back to the CLI default
    (private projects suppressed)."""
    import argparse

    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "out"

    # No `include_private_projects` attribute on this Namespace, intentionally.
    pipeline_args = argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="",
        job_text_file=None,
        target_role="Staff Software Engineer",
        output_dir=output_dir,
        processing_mode="raw",
        outputs=("html", "md"),
        template="modern",
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == 0
    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    # Default behavior: canonical visibility is private, so section is suppressed.
    assert "<h2>Independent Projects</h2>" not in html_text


def test_independent_projects_processed_mode_respects_visibility_flag(
    tmp_path: Path,
) -> None:
    """Processed-mode pipeline both omits and includes the section under the flag."""
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    suppressed_dir = tmp_path / "suppressed"
    suppressed_result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=suppressed_dir,
        extra_args=("--processing-mode", "processed"),
    )
    assert suppressed_result.returncode == 0, suppressed_result.stderr
    suppressed_html = (
        suppressed_dir / "resumes" / "latest_resume_processed.html"
    ).read_text(encoding="utf-8")
    suppressed_md = (
        suppressed_dir / "resumes" / "latest_resume_processed.md"
    ).read_text(encoding="utf-8")
    suppressed_snapshot = json.loads(
        (
            suppressed_dir / "resumes" / "latest_resume_processed_ir_snapshot.json"
        ).read_text(encoding="utf-8")
    )
    assert "<h2>Independent Projects</h2>" not in suppressed_html
    assert "## Independent Projects" not in suppressed_md
    assert int(suppressed_snapshot["independent_projects_count"]) == 0

    included_dir = tmp_path / "included"
    included_result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=included_dir,
        extra_args=("--processing-mode", "processed", "--include-private-projects"),
    )
    assert included_result.returncode == 0, included_result.stderr
    included_html = (
        included_dir / "resumes" / "latest_resume_processed.html"
    ).read_text(encoding="utf-8")
    included_md = (included_dir / "resumes" / "latest_resume_processed.md").read_text(
        encoding="utf-8"
    )
    included_snapshot = json.loads(
        (
            included_dir / "resumes" / "latest_resume_processed_ir_snapshot.json"
        ).read_text(encoding="utf-8")
    )
    assert "<h2>Independent Projects</h2>" in included_html
    assert "## Independent Projects" in included_md
    assert int(included_snapshot["independent_projects_count"]) >= 3


# --- #311: --for-upload + --no-cross-org + --no-selected-achievements ---

_CROSS_ORG_HEADING_HTML = "<h2>Cross-Org Architectural Leadership</h2>"
_CROSS_ORG_HEADING_MD = "## Cross-Org Architectural Leadership"
_SELECTED_HEADING_HTML = "<h2>Selected Achievements</h2>"
_SELECTED_HEADING_MD = "## Selected Achievements"


def _render_with(tmp_path: Path, *flags: str) -> tuple[str, str, dict[str, Any]]:
    """Run CLI with optional flags and return (html, md, ir_snapshot) for the raw artifact.

    Returning the snapshot too lets tests lock in the "all generated artifacts"
    contract: when the flags are set, the IR snapshot's
    cross_org_architectural_leadership_count / selected_achievements_count
    must drop to 0 — not just the rendered HTML/MD section headings.
    """
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "out"
    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
        extra_args=tuple(flags),
    )
    assert result.returncode == 0, result.stderr
    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    return html_text, md_text, snapshot


def test_for_upload_flags_default_off_renders_both_narrative_sections(
    tmp_path: Path,
) -> None:
    """Sanity baseline: with no new flags, both sections render and snapshot counts are non-zero."""
    html_text, md_text, snapshot = _render_with(tmp_path)
    assert _CROSS_ORG_HEADING_HTML in html_text
    assert _CROSS_ORG_HEADING_MD in md_text
    assert _SELECTED_HEADING_HTML in html_text
    assert _SELECTED_HEADING_MD in md_text
    assert int(snapshot["cross_org_architectural_leadership_count"]) > 0
    assert int(snapshot["selected_achievements_count"]) > 0


def test_for_upload_suppresses_both_narrative_sections(tmp_path: Path) -> None:
    """--for-upload is sugar for --no-cross-org + --no-selected-achievements,
    and the suppression is reflected in the IR snapshot too — locking in the
    'all generated artifacts' contract from the CLI help text."""
    html_text, md_text, snapshot = _render_with(tmp_path, "--for-upload")
    assert _CROSS_ORG_HEADING_HTML not in html_text
    assert _CROSS_ORG_HEADING_MD not in md_text
    assert _SELECTED_HEADING_HTML not in html_text
    assert _SELECTED_HEADING_MD not in md_text
    assert int(snapshot["cross_org_architectural_leadership_count"]) == 0
    assert int(snapshot["selected_achievements_count"]) == 0


def test_no_cross_org_suppresses_only_cross_org(tmp_path: Path) -> None:
    """Granular flag isolates suppression to its named section in both render
    and snapshot."""
    html_text, md_text, snapshot = _render_with(tmp_path, "--no-cross-org")
    assert _CROSS_ORG_HEADING_HTML not in html_text
    assert _CROSS_ORG_HEADING_MD not in md_text
    assert _SELECTED_HEADING_HTML in html_text
    assert _SELECTED_HEADING_MD in md_text
    assert int(snapshot["cross_org_architectural_leadership_count"]) == 0
    assert int(snapshot["selected_achievements_count"]) > 0


def test_no_selected_achievements_suppresses_only_selected_achievements(
    tmp_path: Path,
) -> None:
    """Granular flag isolates suppression to its named section in both render
    and snapshot."""
    html_text, md_text, snapshot = _render_with(tmp_path, "--no-selected-achievements")
    assert _SELECTED_HEADING_HTML not in html_text
    assert _SELECTED_HEADING_MD not in md_text
    assert _CROSS_ORG_HEADING_HTML in html_text
    assert _CROSS_ORG_HEADING_MD in md_text
    assert int(snapshot["selected_achievements_count"]) == 0
    assert int(snapshot["cross_org_architectural_leadership_count"]) > 0


def test_run_pipeline_tolerates_namespace_without_for_upload_flags(
    tmp_path: Path,
) -> None:
    """Programmatic callers that build a Namespace by hand must not break — the
    defensive getattr in run_pipeline should fall back to the CLI default
    (no suppression) when for_upload/no_cross_org/no_selected_achievements
    are absent from the Namespace."""
    import argparse

    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "out"

    # No for_upload / no_cross_org / no_selected_achievements on this Namespace, intentionally.
    pipeline_args = argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="",
        job_text_file=None,
        target_role="Staff Software Engineer",
        output_dir=output_dir,
        processing_mode="raw",
        outputs=("html", "md"),
        template="modern",
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == 0
    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    # Default behavior: both narrative sections render.
    assert _CROSS_ORG_HEADING_HTML in html_text
    assert _SELECTED_HEADING_HTML in html_text


def test_for_upload_processed_mode_suppresses_in_all_artifacts(
    tmp_path: Path,
) -> None:
    """Processed-mode coverage: --for-upload is the typical use (processed is the
    default mode). Verifies headings absent from processed-mode HTML/MD AND
    counts drop to 0 in latest_resume_processed_ir_snapshot.json — the path
    where _compute_bullet_line_budget() actually consults the resume IR and
    where the freed layout budget can shift bullet/skill selection."""
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    output_dir = tmp_path / "out"
    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
        extra_args=("--processing-mode", "processed", "--for-upload"),
    )
    assert result.returncode == 0, result.stderr
    html_text = (output_dir / "resumes" / "latest_resume_processed.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_processed.md").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_processed_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert _CROSS_ORG_HEADING_HTML not in html_text
    assert _CROSS_ORG_HEADING_MD not in md_text
    assert _SELECTED_HEADING_HTML not in html_text
    assert _SELECTED_HEADING_MD not in md_text
    assert int(snapshot["cross_org_architectural_leadership_count"]) == 0
    assert int(snapshot["selected_achievements_count"]) == 0


def test_independent_projects_url_normalization_and_safety(tmp_path: Path) -> None:
    """Loader prepends https:// to bare domains and rejects unsafe schemes."""
    items = """
[[independent_projects.items]]
name = "Bare Domain"
summary = "Bare domain URL gets https:// prepended."
key_skills = ["Python"]
source_bullet_ids = ["exp-acme-b1"]
url = "github.com/example/repo"

[[independent_projects.items]]
name = "Bare Domain Port"
summary = "Bare domain:port URL gets https:// prepended."
key_skills = ["Python"]
source_bullet_ids = ["exp-acme-b1"]
url = "github.com:8443/org/repo"

[[independent_projects.items]]
name = "Unsafe Scheme"
summary = "Unsafe scheme is dropped."
key_skills = ["Python"]
source_bullet_ids = ["exp-acme-b1"]
url = "javascript:alert(1)"

[[independent_projects.items]]
name = "Already Https"
summary = "https URL passes through unchanged."
key_skills = ["Python"]
source_bullet_ids = ["exp-acme-b1"]
url = "https://example.com/full"
"""
    experience_db = tmp_path / "experience_db.toml"
    experience_db.write_text(
        _independent_projects_test_experience_db(visibility="public", items=items),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_build_resume_cli(
        experience_db=experience_db,
        profile_path=profile_path,
        output_dir=output_dir,
    )
    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )

    # Bare domain becomes https://
    assert 'href="https://github.com/example/repo"' in html_text
    assert "[Bare Domain](https://github.com/example/repo)" in md_text
    # Bare domain:port also becomes https:// (not dropped as an unknown scheme)
    assert 'href="https://github.com:8443/org/repo"' in html_text
    assert "[Bare Domain Port](https://github.com:8443/org/repo)" in md_text
    # javascript: scheme is dropped (name renders without anchor / link)
    assert "javascript:" not in html_text
    assert "javascript:" not in md_text
    assert "<strong>Unsafe Scheme</strong>" in html_text
    assert "- **Unsafe Scheme**" in md_text
    # Pre-formed https passes through
    assert 'href="https://example.com/full"' in html_text
    assert "[Already Https](https://example.com/full)" in md_text


def test_independent_projects_public_empty_section_omitted(tmp_path: Path) -> None:
    """A public section with no items still omits the header."""
    experience_db = tmp_path / "experience_db.toml"
    experience_db.write_text(
        _independent_projects_test_experience_db(visibility="public", items=""),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_build_resume_cli(
        experience_db=experience_db,
        profile_path=profile_path,
        output_dir=output_dir,
    )
    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    md_text = (output_dir / "resumes" / "latest_resume_raw.md").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert "<h2>Independent Projects</h2>" not in html_text
    assert "## Independent Projects" not in md_text
    assert int(snapshot["independent_projects_count"]) == 0
    assert snapshot["independent_projects_visibility"] == "public"


def test_build_resume_cli_generates_baseline_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "baseline"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--profile",
            str(profile_path),
            "--output-dir",
            str(output_dir),
            "--target-role",
            "Staff Software Engineer",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    html_path = output_dir / "resumes" / "latest_resume_raw.html"
    modern_html_path = output_dir / "resumes" / "latest_modern_resume_raw.html"
    md_path = output_dir / "resumes" / "latest_resume_raw.md"
    snapshot_path = output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json"
    text_snapshot_path = output_dir / "resumes" / "latest_resume_raw_ir_snapshot.txt"

    assert html_path.exists()
    assert modern_html_path.exists()
    assert md_path.exists()
    assert snapshot_path.exists()
    assert text_snapshot_path.exists()

    html_text = html_path.read_text(encoding="utf-8")
    modern_html_text = modern_html_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    text_snapshot = text_snapshot_path.read_text(encoding="utf-8")
    profile = load_profile(profile_path)
    expected_linkedin = _build_linkedin_url(profile.linkedin)
    expected_github = _build_github_url(profile.github)

    assert profile.name in html_text
    assert '<p class="headline">Staff Software Engineer</p>' not in html_text
    assert "Staff Software Engineer" not in md_text
    assert _expected_resume_title(profile) in html_text
    assert expected_linkedin in html_text
    if profile.github:
        assert expected_github in html_text
    else:
        assert "github.com/" not in html_text
    assert "Lead Framework Designer, Python Test Framework (Video)" in html_text
    assert "HP / Poly (formerly Polycom), Austin, TX" in html_text
    assert (
        ".company-line span { margin-left: auto; text-align: right; font-size: 10pt; color: #222; font-weight: 700; }"
        in html_text
    )
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert "<h2>Summary</h2>" not in html_text
    assert (
        f'<p class="resume-title"><strong>{_expected_resume_title(profile)}</strong></p>'
        in html_text
    )
    assert html_text.index('class="resume-title"') < html_text.index(
        "<h2>Key Skills and Expertise</h2>"
    )
    assert '<hr class="header-divider" />' in html_text
    assert ".header-divider { border: 0; border-top: 1px solid #000;" in html_text
    assert "h2 { font-size: 12pt;" in html_text
    assert html_text.index("<h2>Key Skills and Expertise</h2>") < html_text.index(
        "<h2>Professional Experience</h2>"
    )
    assert "<h2>Cross-Org Architectural Leadership</h2>" in html_text
    assert html_text.index("<h2>Key Skills and Expertise</h2>") < html_text.index(
        "<h2>Cross-Org Architectural Leadership</h2>"
    )
    assert html_text.index(
        "<h2>Cross-Org Architectural Leadership</h2>"
    ) < html_text.index("<h2>Professional Experience</h2>")
    assert "<h2>Selected Achievements</h2>" in html_text
    assert html_text.index(
        "<h2>Cross-Org Architectural Leadership</h2>"
    ) < html_text.index("<h2>Selected Achievements</h2>")
    assert html_text.index("<h2>Selected Achievements</h2>") < html_text.index(
        "<h2>Professional Experience</h2>"
    )
    assert ".header { text-align: center; margin: 0;" in modern_html_text
    # Both templates left-align info-item sections.
    assert (
        ".info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left;"
        in html_text
    )
    assert (
        ".info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left;"
        in modern_html_text
    )
    assert " • " in html_text
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
    assert md_text.index("## Summary") < md_text.index("## Key Skills and Expertise")
    assert "## Cross-Org Architectural Leadership" in md_text
    assert md_text.index("## Key Skills and Expertise") < md_text.index(
        "## Cross-Org Architectural Leadership"
    )
    assert md_text.index("## Cross-Org Architectural Leadership") < md_text.index(
        "## Professional Experience"
    )
    assert "## Selected Achievements" in md_text
    assert md_text.index("## Cross-Org Architectural Leadership") < md_text.index(
        "## Selected Achievements"
    )
    assert md_text.index("## Selected Achievements") < md_text.index(
        "## Professional Experience"
    )
    assert " • " in md_text
    if expected_linkedin:
        assert expected_linkedin in md_text
    if expected_github:
        assert expected_github in md_text
    assert snapshot["profile"]["linkedin"] == profile.linkedin
    assert snapshot["profile"]["linkedin_url"] == expected_linkedin
    assert snapshot["profile"]["github"] == profile.github
    assert snapshot["profile"]["github_url"] == expected_github
    assert "Programming Debugging & Engineering Fundamentals" in md_text
    assert "Python" in md_text
    assert "Java" in md_text
    assert int(snapshot["skills_category_count"]) == 5
    assert int(snapshot["selected_achievements_count"]) >= 3
    assert "summary:" in text_snapshot
    assert "skills:" in text_snapshot
    assert "experience:" in text_snapshot
    assert "education:" in text_snapshot
    assert "leadership_community:" in text_snapshot
    assert "selected_achievements:" in text_snapshot
    assert "job_context:" in text_snapshot
    assert f"profile.linkedin_url: {expected_linkedin}" in text_snapshot
    assert f"profile.github_url: {expected_github}" in text_snapshot
    assert text_snapshot.index("summary:") < text_snapshot.index("skills:")
    assert text_snapshot.index("skills:") < text_snapshot.index("experience:")
    assert " • " in text_snapshot


def test_build_resume_cli_processed_mode_applies_filtering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"

    raw_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(raw_dir),
            "--processing-mode",
            "raw",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert raw_result.returncode == 0, raw_result.stderr

    processed_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(processed_dir),
            "--processing-mode",
            "processed",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert processed_result.returncode == 0, processed_result.stderr

    raw_snapshot = json.loads(
        (raw_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    processed_snapshot = json.loads(
        (
            processed_dir / "resumes" / "latest_resume_processed_ir_snapshot.json"
        ).read_text(encoding="utf-8")
    )

    raw_count = int(raw_snapshot["skills_category_count"])
    processed_count = int(processed_snapshot["skills_category_count"])

    assert raw_count >= processed_count
    raw_md = (raw_dir / "resumes" / "latest_resume_raw.md").read_text(encoding="utf-8")
    assert "Programming Debugging & Engineering Fundamentals" in raw_md

    # Issue #42 e2e assertion: processed rendered skills stay in 11-13 lines.
    processed_html = (
        processed_dir / "resumes" / "latest_resume_processed.html"
    ).read_text(encoding="utf-8")
    processed_skills = _extract_skills_by_category_from_html(processed_html)
    assert processed_skills, (
        "Expected parsed skills categories in processed HTML output"
    )

    monkeypatch.setenv("RESUME_FONT_STRICT", "0")
    font_regular, font_bold, font_name = load_font_pair(require_calibri=False)
    report = measure_skills_section(
        processed_skills,
        font_regular=font_regular,
        font_bold=font_bold,
        font_name=font_name,
    )
    total_lines = int(report["summary"]["total_lines"])
    # Staff-level bucket consolidation can trim one extra rendered line while
    # still preserving high-signal coverage in processed mode.
    min_lines = max(1, TARGET_LINES_MIN - 1)
    assert min_lines <= total_lines <= TARGET_LINES_MAX, (
        f"Expected processed skills lines in {min_lines}-{TARGET_LINES_MAX}; "
        f"got {total_lines}"
    )


def test_build_resume_cli_modern_template_renders_centered_header(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "modern"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--template",
            "modern",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    html_text = (output_dir / "resumes" / "latest_modern_resume_raw.html").read_text(
        encoding="utf-8"
    )
    assert '<div class="header">' in html_text
    assert ".header { text-align: center; margin: 0;" in html_text
    assert "body { font-family: Carlito, Calibri, Arial, sans-serif;" in html_text
    assert "font-size: 11pt; line-height: 1.22;" in html_text
    assert "h2 { font-size: 12pt;" in html_text
    assert "text-align: center; width: 100%; display: block;" in html_text
    assert "border-bottom: 1px solid #ccc;" in html_text
    assert "margin: 12px 0 16px 0;" in html_text
    assert "padding-bottom: 0px;" in html_text
    assert (
        ".skills-category { margin: 0 0 3px 0; font-size: 10.5pt; text-align: center; }"
        in html_text
    )
    assert (
        ".info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left; }"
        in html_text
    )
    assert ".resume-title" in html_text
    assert '<hr class="header-divider" />' in html_text
    assert ".header-divider { border: 0; border-top: 1px solid #000;" in html_text
    assert ".target-role { margin: 1px 0 0 0;" in html_text
    assert "<h2>Summary</h2>" not in html_text
    # Modern template must NOT re-emit the duplicate headline element
    assert '<p class="headline">' not in html_text
    # Education / leadership sections must be left-aligned in the modern template
    assert (
        ".info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left;"
        in html_text
    )


def test_build_resume_cli_processed_mode_does_not_mutate_experience_db(
    tmp_path: Path,
) -> None:
    experience_db = REPO_ROOT / "data" / "experience" / "experience_db.toml"
    before_bytes = experience_db.read_bytes()

    output_dir = tmp_path / "processed_immutability"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert experience_db.read_bytes() == before_bytes


def test_has_measurable_outcome_detects_quantified_impact_language() -> None:
    assert _has_measurable_outcome("Reduced flaky failures by 37 percent.")
    assert _has_measurable_outcome("Improved pipeline runtime 2x after refactor.")
    assert _has_measurable_outcome(
        "Eliminating manual release tagging across 15 projects through automation."
    )
    assert _has_measurable_outcome(
        "Reducing duplicate framework spike efforts by forty percent across teams."
    )
    assert not _has_measurable_outcome(
        "Improved framework quality through better architecture decisions."
    )


def test_build_resume_cli_processed_mode_emits_gap_summary_for_job_text(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "processed_gap"
    job_text_file = tmp_path / "job_text.txt"
    job_text_file.write_text(
        (
            "Staff SDET focused on fraud prevention, risk analytics, and payments APIs. "
            "Expect deep CI/CD, observability, and compliance automation ownership."
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html",
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--job-text-file",
            str(job_text_file),
            "--company",
            "smoke",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    gap_summary_path = (
        output_dir / "resumes" / "latest_resume_processed_gap_summary.json"
    )
    assert gap_summary_path.exists()
    payload = json.loads(gap_summary_path.read_text(encoding="utf-8"))
    assert "missing_terms" in payload
    assert isinstance(payload["missing_terms"], list)


def test_build_resume_cli_processed_mode_emits_decision_report_for_job_text(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "processed_decision_report"
    job_text_file = tmp_path / "job_text.txt"
    job_text_file.write_text(
        (
            "Staff SDET focused on fraud prevention, risk analytics, and payments APIs. "
            "Expect deep CI/CD, observability, and compliance automation ownership."
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html",
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--job-text-file",
            str(job_text_file),
            "--company",
            "smoke",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    decision_report_path = (
        output_dir / "resumes" / "latest_resume_processed_decision_report.json"
    )
    assert decision_report_path.exists()
    payload = json.loads(decision_report_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == build_resume.DECISION_REPORT_SCHEMA_VERSION
    assert payload["processing_mode"] == "processed"
    assert set(payload["bullets"].keys()) == {"selected", "rejected"}
    assert isinstance(payload["bullets"]["selected"], list)
    assert isinstance(payload["bullets"]["rejected"], list)
    skills = payload["skills"]
    for required_key in (
        "categories_before",
        "categories_after",
        "category_merges",
        "category_renames",
        "categories_dropped",
        "skill_moves",
        "skills_dropped",
        "inferred_skills",
    ):
        assert required_key in skills, required_key
    coverage = payload["jd_coverage"]
    for required_key in (
        "job_term_count",
        "unique_job_term_count",
        "covered_term_count",
        "missing_term_count",
        "covered_terms",
        "missing_terms",
    ):
        assert required_key in coverage, required_key
    if payload["bullets"]["selected"]:
        first_selected = payload["bullets"]["selected"][0]
        for required_key in (
            "bullet_id",
            "experience_id",
            "position",
            "text",
            "skills",
            "confidence",
            "tags",
            "has_measurable_outcome",
        ):
            assert required_key in first_selected, required_key


def test_write_decision_report_records_bullet_rejection_reasons(tmp_path: Path) -> None:
    profile = load_profile(_TRACKED_PROFILE_PATH)
    experience_with_duplicate = Experience(
        id="exp-test",
        job_title="Staff SDET",
        company="Acme",
        start_date="2020-01",
        end_date="present",
        general_role_description="Ship reliability tooling.",
        related_skills=("python",),
        bullets=(
            Bullet(
                id="b1",
                text="Built CI gating to reduce flaky failures by 30%.",
                skills=("ci", "python"),
                impact_type="reliability",
                domain="qa",
            ),
            Bullet(
                id="b2",
                text="Built CI gating to reduce flaky failures by 30%.",
                skills=("ci", "python"),
                impact_type="reliability",
                domain="qa",
            ),
            Bullet(
                id="b3",
                text="Designed observability dashboards for payments.",
                skills=("observability",),
                impact_type="visibility",
                domain="ops",
            ),
        ),
    )
    baseline_resume = build_resume.ResumeIR(
        profile=profile,
        target_role="Staff SDET",
        target_company="Acme",
        display_headline="Staff SDET",
        job_context=None,
        experiences=(experience_with_duplicate,),
        skills_by_category={"Quality": ["python", "ci"], "Cloud": ["aws"]},
    )

    final_experience = Experience(
        id="exp-test",
        job_title="Staff SDET",
        company="Acme",
        start_date="2020-01",
        end_date="present",
        general_role_description="Ship reliability tooling.",
        related_skills=("python",),
        bullets=(
            experience_with_duplicate.bullets[0],
            experience_with_duplicate.bullets[2],
        ),
    )
    final_resume = build_resume.ResumeIR(
        profile=profile,
        target_role="Staff SDET",
        target_company="Acme",
        display_headline="Staff SDET",
        job_context=None,
        experiences=(final_experience,),
        skills_by_category={"Quality & Cloud": ["python", "ci", "aws"]},
    )
    removal_reasons = {"b2": "duplicate"}

    output_path = tmp_path / "decision_report.json"
    build_resume.write_decision_report(
        final_resume,
        baseline_resume,
        removal_reasons=removal_reasons,
        output_path=output_path,
    )
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == build_resume.DECISION_REPORT_SCHEMA_VERSION
    selected_ids = {item["bullet_id"] for item in payload["bullets"]["selected"]}
    assert selected_ids == {"b1", "b3"}
    rejected = payload["bullets"]["rejected"]
    assert len(rejected) == 1
    assert rejected[0]["bullet_id"] == "b2"
    assert rejected[0]["reason"] == "duplicate"
    skills = payload["skills"]
    assert skills["categories_dropped"] == ["Cloud", "Quality"]
    merge_targets = {entry["into"] for entry in skills["category_merges"]}
    assert merge_targets == {"Quality & Cloud"}
    assert "aws" not in skills["skills_dropped"]


def test_trim_by_rules_populates_removal_reasons_for_duplicate_bullets() -> None:
    profile = load_profile(_TRACKED_PROFILE_PATH)
    experience = Experience(
        id="exp-trim",
        job_title="Staff SDET",
        company="Acme",
        start_date="2020-01",
        end_date="present",
        general_role_description="Ship reliability tooling.",
        related_skills=("python",),
        bullets=(
            Bullet(
                id="b-keep-1",
                text="Built CI gating to reduce flaky failures by 30%.",
                skills=("ci",),
                impact_type="reliability",
                domain="qa",
            ),
            Bullet(
                id="b-keep-2",
                text="Designed observability dashboards for payments.",
                skills=("observability",),
                impact_type="visibility",
                domain="ops",
            ),
            Bullet(
                id="b-dup",
                text="Built CI gating to reduce flaky failures by 30%.",
                skills=("ci",),
                impact_type="reliability",
                domain="qa",
            ),
            Bullet(
                id="b-keep-3",
                text="Refactored deployment automation across services.",
                skills=("ci",),
                impact_type="velocity",
                domain="ops",
            ),
        ),
    )
    resume = build_resume.ResumeIR(
        profile=profile,
        target_role="Staff SDET",
        target_company="Acme",
        display_headline="Staff SDET",
        job_context=None,
        experiences=(experience,),
        skills_by_category={"Quality": ["python", "ci"]},
    )

    removal_reasons: dict[str, str] = {}
    trimmed = trim_by_rules(resume, removal_reasons=removal_reasons)

    surviving_ids = {bullet.id for bullet in trimmed.experiences[0].bullets}
    assert "b-dup" not in surviving_ids
    assert removal_reasons.get("b-dup") == "duplicate"


def test_build_resume_cli_rejects_unknown_template(tmp_path: Path) -> None:
    output_dir = tmp_path / "invalid_template"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(output_dir),
            "--template",
            "does-not-exist",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Template 'does-not-exist' not found" in result.stderr


def test_derive_resume_title_adds_missing_seniority_from_headline() -> None:
    profile = load_profile(_TRACKED_PROFILE_PATH)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )
    adjusted = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline="Staff Software Engineer | Test Automation and Framework Architecture",
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=resume.enrichment_by_bullet_id,
    )

    assert derive_resume_title(adjusted) == PROFILE_RESUME_TITLE


def test_derive_resume_title_preserves_senior_sdet_without_special_expansion() -> None:
    """Senior SDET is now treated as any other role, not specially expanded."""
    profile = load_profile(_TRACKED_PROFILE_PATH)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    assert derive_resume_title(resume) == PROFILE_RESUME_TITLE


def test_derive_resume_title_ignores_target_role_when_headline_is_blank() -> None:
    profile = build_resume.Profile(
        name="Test Person",
        headline="Staff Test Architect",
        location="Austin, TX",
        email="test@example.com",
        phone="555-0100",
        website="example.com",
        linkedin="linkedin.com/in/test",
        github="github.com/test",
        summary="Drives automation architecture across teams.",
        education_entries=(),
        leadership_community_entries=(),
    )
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    blank_profile = type(profile)(
        name=profile.name,
        headline="",
        location=profile.location,
        email=profile.email,
        phone=profile.phone,
        website=profile.website,
        linkedin=profile.linkedin,
        github=profile.github,
        summary=profile.summary,
        education_entries=profile.education_entries,
        leadership_community_entries=profile.leadership_community_entries,
    )
    resume = assemble_baseline_resume(
        profile=blank_profile,
        target_role="Graphcore Senior Principal Test Framework Software Engineer",
        target_company="Graphcore",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior Principal Test Framework Software Engineer\n"
            "Company: Graphcore"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    assert derive_resume_title(resume) == "Software Test Automation Engineer"


def test_display_company_header_maps_hp_poly_aliases() -> None:
    cases = [
        ("HP / Poly", "HP / Poly (formerly Polycom), Austin, TX"),
        ("HP/Poly", "HP / Poly (formerly Polycom), Austin, TX"),
        ("Poly", "HP / Poly (formerly Polycom), Austin, TX"),
        ("Polycom", "HP / Poly (formerly Polycom), Austin, TX"),
    ]
    for company, expected in cases:
        assert _display_company_header(company) == expected


def test_build_resume_cli_accepts_job_url_and_generates_job_context(
    tmp_path: Path,
) -> None:
    """Use the saved Schwab page fixture so the test is fully offline/deterministic.

    The fixture was captured from:
      https://www.schwabjobs.com/job/austin/sr-sdet-workplace-services-engineering/33727/92422911552
    and contains the real metadata served by schwabjobs.com.
    """
    output_dir = tmp_path / "from_job_url"
    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = str(SCHWAB_FIXTURE)
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--job-url",
            SCHWAB_JOB_URL,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    html_text = (output_dir / "resumes" / "latest_resume_raw.html").read_text(
        encoding="utf-8"
    )
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert '<p class="headline">Sr. SDET</p>' not in html_text
    assert snapshot["job_context"]["role_hint"] == "Sr. SDET"
    assert snapshot["target_company"] == "Charles Schwab"
    assert snapshot["job_context"]["source"] == "company-site"
    assert snapshot["job_context"]["job_id"] == "92422911552"
    assert snapshot["job_context"]["input_url"] == SCHWAB_JOB_URL
    assert snapshot["job_context"]["fetch_status"] == "fetched"
    assert not (output_dir / "charles_schwab_resume_raw.html").exists()
    assert not (output_dir / "charles_schwab_modern_resume_raw.html").exists()
    assert not (output_dir / "charles_schwab_resume_raw.md").exists()
    assert not (output_dir / "charles_schwab_resume_raw_ir_snapshot.json").exists()
    assert not (output_dir / "charles_schwab_resume_raw_ir_snapshot.txt").exists()


def test_build_resume_cli_job_url_snapshot_contract_is_complete_and_deterministic(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "job_url_snapshot_contract"
    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = str(SCHWAB_FIXTURE)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--job-url",
            SCHWAB_JOB_URL,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    job_context = snapshot["job_context"]

    assert job_context["normalized_url"] == SCHWAB_JOB_URL
    assert job_context["page_title"].strip() != ""
    assert 0 < len(job_context["description_excerpt"]) <= 500
    assert isinstance(job_context["notes"], list)
    assert job_context["notes"] == ["fixture:schwab_sr_sdet.html"]

    assert job_context["company_research"]["strategy"] == "deterministic-v1"
    assert job_context["company_research"]["confidence"] == "low"
    assert (
        "Public listing signals only" in job_context["company_research"]["product_hint"]
    )


def test_build_resume_cli_explicit_target_role_overrides_job_context_hint(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "explicit_target_role"
    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = str(SCHWAB_FIXTURE)
    explicit_target_role = "Principal QA Automation Engineer"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--job-url",
            SCHWAB_JOB_URL,
            "--target-role",
            explicit_target_role,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        check=False,
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert snapshot["target_role"] == explicit_target_role
    assert snapshot["job_context"]["role_hint"] == "Sr. SDET"


def test_build_resume_cli_rejects_job_url_and_job_text_file_together(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "conflicting_job_inputs"
    job_text_file = tmp_path / "job_description.txt"
    job_text_file.write_text("Job Title: Senior SDET\n", encoding="utf-8")
    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = str(SCHWAB_FIXTURE)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(output_dir),
            "--job-url",
            SCHWAB_JOB_URL,
            "--job-text-file",
            str(job_text_file),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "Provide only one of --job-url or --job-text-file" in result.stderr


def test_build_resume_cli_accepts_job_text_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "from_job_text"

    job_text_file = tmp_path / "job_description.txt"
    job_text_file.write_text(
        "\n".join(
            [
                "Job Title: Senior SDET",
                "Company: Charles Schwab",
                "We are looking for a Senior SDET to join our workplace services team.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--job-text-file",
            str(job_text_file),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert snapshot["target_role"] == "Senior SDET"
    assert snapshot["target_company"] == "Charles Schwab"
    assert snapshot["job_context"]["source"] == "job-text-file"
    assert snapshot["job_context"]["fetch_status"] == "provided_text"
    assert snapshot["job_context"]["company_research"]["strategy"] == "deterministic-v1"
    assert (
        snapshot["job_context"]["company_research"]["company_name"] == "Charles Schwab"
    )


def test_build_resume_cli_job_text_without_company_omits_company_research(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "job_text_without_company"
    job_text_file = tmp_path / "job_description.txt"
    job_text_file.write_text(
        "Job Title: Senior SDET\nLooking for a Senior SDET focused on CI reliability.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(output_dir),
            "--job-text-file",
            str(job_text_file),
            "--company",
            "smoke",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    snapshot = json.loads(
        (output_dir / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )

    assert snapshot["target_role"] == "Senior SDET"
    assert snapshot["target_company"] == ""
    assert snapshot["job_context"]["company_name"] == ""
    assert "company_research" not in snapshot["job_context"]


def test_ingest_job_context_rejects_blocked_fixture_env_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_fixture = REPO_ROOT / "data" / "samples" / "job_page_fixture.html"
    monkeypatch.setenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", str(blocked_fixture))

    with pytest.raises(ValueError, match="blocked runtime directory"):
        ingest_job_context(SCHWAB_JOB_URL)


def test_build_resume_cli_rejects_typo_hjob_text_file_flag(tmp_path: Path) -> None:
    output_dir = tmp_path / "invalid_flag"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--output-dir",
            str(output_dir),
            "--hjob-text-file",
            "job.txt",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--hjob-text-file" in result.stderr


def test_build_resume_cli_deduplicates_equivalent_headline_and_resume_title(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "processed"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--profile",
            str(_TRACKED_PROFILE_PATH),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    modern_html = (output_dir / "resumes" / "latest_resume_processed.html").read_text(
        encoding="utf-8"
    )
    default_html = (
        output_dir / "resumes" / "latest_default_resume_processed.html"
    ).read_text(encoding="utf-8")

    assert f'<p class="headline">{PROFILE_HEADLINE}</p>' not in modern_html
    assert f'<p class="headline">{PROFILE_HEADLINE}</p>' not in default_html
    assert (
        f'<p class="resume-title"><strong>{PROFILE_RESUME_TITLE}</strong></p>'
        in modern_html
    )
    assert (
        f'<p class="resume-title"><strong>{PROFILE_RESUME_TITLE}</strong></p>'
        in default_html
    )


def test_collect_resume_skill_signals_is_relevance_weighted_and_deterministic() -> None:
    profile = build_resume.Profile(
        name="Test Person",
        headline="Staff Test Architect",
        location="Austin, TX",
        email="test@example.com",
        phone="555-0100",
        website="example.com",
        linkedin="linkedin.com/in/test",
        github="github.com/test",
        summary="Drives automation architecture across teams.",
        education_entries=(),
        leadership_community_entries=(),
    )
    bullet_low = Bullet(
        id="b-low",
        text="Low relevance work.",
        skills=("SkillLow",),
        impact_type="reliability",
        domain="video",
    )
    bullet_high = Bullet(
        id="b-high",
        text="High relevance work.",
        skills=("SkillHigh",),
        impact_type="reliability",
        domain="video",
    )
    experience = Experience(
        id="exp-test",
        job_title="Role",
        company="Company",
        start_date="2020-01",
        end_date="2021-01",
        general_role_description="Did relevant work.",
        related_skills=("SkillRelated",),
        bullets=(bullet_low, bullet_high),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(experience,),
        skills_by_category={
            "zeta": ["SkillLow"],
            "alpha": ["SkillHigh"],
        },
    )
    scored_resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "b-low": {"confidence": 0.1},
            "b-high": {"confidence": 0.95},
        },
    )

    assert _collect_resume_skill_signals(scored_resume)[:2] == [
        "SkillHigh",
        "SkillLow",
    ]


def test_collect_resume_skill_signals_is_stable_across_order_churn() -> None:
    profile = load_profile(PROFILE)
    bullet_a = Bullet(
        id="b-a",
        text="Service diagnostics.",
        skills=("Service Diagnostics",),
        impact_type="reliability",
        domain="video",
    )
    bullet_b = Bullet(
        id="b-b",
        text="Automation architecture.",
        skills=("Automation Architecture",),
        impact_type="reliability",
        domain="video",
    )

    base_experience = Experience(
        id="exp-churn-a",
        job_title="Role A",
        company="Company",
        start_date="2020-01",
        end_date="2021-01",
        general_role_description="Built and stabilized automation systems.",
        related_skills=("Service Diagnostics",),
        bullets=(bullet_a, bullet_b),
    )
    churned_experience = Experience(
        id="exp-churn-a",
        job_title="Role A",
        company="Company",
        start_date="2020-01",
        end_date="2021-01",
        general_role_description="Built and stabilized automation systems.",
        related_skills=("Service Diagnostics",),
        bullets=(bullet_b, bullet_a),
    )

    base_resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(base_experience,),
        skills_by_category={
            "Platform": ["Automation Architecture", "Service Diagnostics"],
            "Tooling": ["Python"],
        },
    )
    churned_resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(churned_experience,),
        skills_by_category={
            "Tooling": ["Python"],
            "Platform": ["Service Diagnostics", "Automation Architecture"],
        },
    )

    base_scored = type(base_resume)(
        profile=base_resume.profile,
        target_role=base_resume.target_role,
        target_company=base_resume.target_company,
        display_headline=base_resume.display_headline,
        job_context=base_resume.job_context,
        experiences=base_resume.experiences,
        skills_by_category=base_resume.skills_by_category,
        enrichment_by_bullet_id={
            "b-a": {"confidence": 0.95},
            "b-b": {"confidence": 0.60},
        },
    )
    churned_scored = type(churned_resume)(
        profile=churned_resume.profile,
        target_role=churned_resume.target_role,
        target_company=churned_resume.target_company,
        display_headline=churned_resume.display_headline,
        job_context=churned_resume.job_context,
        experiences=churned_resume.experiences,
        skills_by_category=churned_resume.skills_by_category,
        enrichment_by_bullet_id={
            "b-a": {"confidence": 0.95},
            "b-b": {"confidence": 0.60},
        },
    )

    base_signals = _collect_resume_skill_signals(base_scored)
    churned_signals = _collect_resume_skill_signals(churned_scored)

    assert base_signals == churned_signals
    assert base_signals[0] == "Service Diagnostics"


def test_ingest_job_context_extracts_role_company_and_research() -> None:
    url = (
        "https://www.linkedin.com/jobs/view/4380299765/?"
        "currentJobId=4380299765&keywords=SDET"
    )

    def fake_fetcher(_: str) -> FetchedPage:
        return FetchedPage(
            status="fetched",
            title="Senior SDET - Contoso - Austin, Texas | LinkedIn",
            description="Contoso is looking for a Senior SDET to join our quality team.",
            notes=(),
        )

    context = ingest_job_context(url, fetcher=fake_fetcher)

    assert context.source == "linkedin"
    assert context.job_id == "4380299765"
    assert context.role_hint == "Senior SDET"
    assert context.company_name == "Contoso"
    assert context.company_research is not None
    assert context.company_research.strategy == "deterministic-v1"


def test_ingest_job_context_falls_back_to_query_keywords() -> None:
    url = (
        "https://www.linkedin.com/jobs/search-results/?"
        "currentJobId=4380299765&keywords=SDET"
    )

    def fake_fetcher(_: str) -> FetchedPage:
        return FetchedPage(
            status="fetch_failed",
            title="",
            description="",
            notes=("fetch_failed:HTTPError",),
        )

    context = ingest_job_context(url, fetcher=fake_fetcher)

    assert context.role_hint == "SDET"
    assert context.company_name == ""
    assert context.fetch_status == "fetch_failed"
    assert context.notes == ("fetch_failed:HTTPError",)


def test_ingest_job_context_extracts_role_and_id_from_company_site_path() -> None:
    def fake_fetcher(_: str) -> FetchedPage:
        return FetchedPage(
            status="fetch_failed",
            title="",
            description="",
            notes=("fetch_failed:HTTPError",),
        )

    context = ingest_job_context(SCHWAB_JOB_URL, fetcher=fake_fetcher)

    assert context.source == "company-site"
    assert context.job_id == "92422911552"
    assert context.role_hint == "Sr SDET Workplace Services Engineering"
    assert context.company_name == "Schwab"


def test_ingest_job_context_rejects_unsupported_url_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        ingest_job_context("file:///tmp/job.html")


def test_ingest_job_context_rejects_localhost_target() -> None:
    with pytest.raises(ValueError, match="localhost"):
        ingest_job_context("http://localhost/jobs/123")


def test_ingest_job_context_rejects_private_ip_target() -> None:
    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("https://10.0.0.5/jobs/123")


def test_ingest_job_context_rejects_hostname_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jd_ingest,
        "_resolve_hostname_ips",
        lambda _hostname: (ipaddress.ip_address("10.0.0.5"),),
    )

    def fail_fetcher(_: str) -> FetchedPage:
        raise AssertionError("fetcher should not be called for private-DNS rejection")

    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("https://jobs.example.com/123", fetcher=fail_fetcher)


def test_ingest_job_context_rejects_hostname_with_mixed_public_and_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jd_ingest,
        "_resolve_hostname_ips",
        lambda _hostname: (
            ipaddress.ip_address("93.184.216.34"),
            ipaddress.ip_address("10.1.2.3"),
        ),
    )

    def fail_fetcher(_: str) -> FetchedPage:
        raise AssertionError("fetcher should not be called for mixed-DNS rejection")

    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("https://jobs.example.com/123", fetcher=fail_fetcher)


def test_ingest_job_context_rejects_hostname_resolving_to_ipv4_mapped_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jd_ingest,
        "_resolve_hostname_ips",
        lambda _hostname: (ipaddress.ip_address("::ffff:127.0.0.1"),),
    )

    def fail_fetcher(_: str) -> FetchedPage:
        raise AssertionError(
            "fetcher should not be called for mapped-loopback DNS rejection"
        )

    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("https://jobs.example.com/123", fetcher=fail_fetcher)


def test_ingest_job_context_allows_dns_lookup_failure_non_strict_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(*_args: object, **_kwargs: object) -> list[object]:
        raise OSError("dns unavailable")

    def fake_fetcher(_: str) -> FetchedPage:
        return FetchedPage(
            status="fetched",
            title="Senior SDET - Contoso",
            description="Role description",
            notes=(),
        )

    monkeypatch.setattr("resume_builder.jd_ingest.socket.getaddrinfo", fake_getaddrinfo)
    context = ingest_job_context("https://jobs.example.com/123", fetcher=fake_fetcher)
    assert context.fetch_status == "fetched"


def test_ingest_job_context_truncates_fetched_description_excerpt() -> None:
    long_description = "x" * 900

    def fake_fetcher(_: str) -> FetchedPage:
        return FetchedPage(
            status="fetched",
            title="Senior SDET - Contoso - Austin, Texas | LinkedIn",
            description=long_description,
            notes=(),
        )

    context = ingest_job_context(SCHWAB_JOB_URL, fetcher=fake_fetcher)

    assert len(context.description_excerpt) == 500
    assert context.description_excerpt == long_description[:500]


def test_redirect_handler_rejects_localhost_redirect_target() -> None:
    handler = jd_ingest._ValidatingRedirectHandler()
    request = Request("https://example.com/jobs/123")
    with pytest.raises(ValueError, match="localhost"):
        handler.redirect_request(
            request,
            fp=io.BytesIO(b""),
            code=302,
            msg="Found",
            headers=HTTPMessage(),
            newurl="http://localhost/internal",
        )


def test_redirect_handler_rejects_private_resolved_redirect_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        jd_ingest,
        "_resolve_hostname_ips",
        lambda _hostname: (ipaddress.ip_address("192.168.1.20"),),
    )
    handler = jd_ingest._ValidatingRedirectHandler()
    request = Request("https://example.com/jobs/123")
    with pytest.raises(ValueError, match="non-public IP"):
        handler.redirect_request(
            request,
            fp=io.BytesIO(b""),
            code=302,
            msg="Found",
            headers=HTTPMessage(),
            newurl="https://redirect.example.internal/jobs/456",
        )


def test_fetch_job_page_metadata_revalidates_dns_before_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)

    resolutions = [
        (ipaddress.ip_address("93.184.216.34"),),
        (ipaddress.ip_address("10.0.0.5"),),
    ]

    def fake_resolve(
        _hostname: str,
    ) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        return resolutions.pop(0)

    class _FailIfOpened:
        def open(self, req: object, timeout: int = 0) -> object:
            del req, timeout
            raise AssertionError(
                "open() should not be called after revalidation failure"
            )

    monkeypatch.setattr(jd_ingest, "_resolve_hostname_ips", fake_resolve)
    monkeypatch.setattr(jd_ingest, "build_opener", lambda *_args: _FailIfOpened())

    context = ingest_job_context("https://jobs.example.com/123")
    assert context.fetch_status == "fetch_failed"
    assert context.notes == ("fetch_failed:ValueError",)


def test_fetch_job_page_metadata_limits_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setattr(
        jd_ingest,
        "_resolve_hostname_ips",
        lambda _hostname: (ipaddress.ip_address("93.184.216.34"),),
    )

    class _FakeHeaders:
        def get_content_charset(self) -> str:
            return "utf-8"

        def get(self, key: str, default: str | None = None) -> str | None:
            return default

    class _FakeResponse:
        headers = _FakeHeaders()

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://example.com/jobs/123"

        def read(self, limit: int = -1) -> bytes:
            assert limit == jd_ingest._MAX_FETCH_BYTES + 1
            return b"x" * (jd_ingest._MAX_FETCH_BYTES + 1)

    class _FakeOpener:
        def open(self, req: object, timeout: int = 0) -> _FakeResponse:
            assert timeout == 8
            return _FakeResponse()

    monkeypatch.setattr(jd_ingest, "build_opener", lambda *args: _FakeOpener())
    fetched = jd_ingest._fetch_job_page_metadata("https://example.com/jobs/123")
    assert fetched.status == "fetch_failed"
    assert fetched.notes == ("fetch_failed:ResponseTooLarge",)


def test_ingest_job_context_rejects_localhost_with_trailing_dot() -> None:
    with pytest.raises(ValueError, match="localhost"):
        ingest_job_context("http://localhost./jobs/123")


def test_ingest_job_context_rejects_link_local_ipv6_zone_id() -> None:
    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("http://[fe80::1%25eth0]/jobs/123")


def test_infer_source_rejects_linkedin_lookalike_domain() -> None:
    from resume_builder.jd_ingest import _infer_source

    assert _infer_source("linkedin.com.evil.com") == "company-site"


def test_infer_source_accepts_linkedin_subdomain() -> None:
    from resume_builder.jd_ingest import _infer_source

    assert _infer_source("www.linkedin.com") == "linkedin"


def test_normalize_linkedin_slug_rejects_company_url() -> None:
    from resume_builder.build_resume import _normalize_linkedin_slug

    assert _normalize_linkedin_slug("https://www.linkedin.com/company/foo") == ""


def test_normalize_linkedin_slug_accepts_in_url() -> None:
    from resume_builder.build_resume import _normalize_linkedin_slug

    assert (
        _normalize_linkedin_slug(
            "https://www.linkedin.com/in/jonathan-j-smith-automation"
        )
        == "jonathan-j-smith-automation"
    )


def test_normalize_github_username_rejects_gist_host() -> None:
    from resume_builder.build_resume import _normalize_github_username

    assert _normalize_github_username("https://gist.github.com/user") == ""


def test_normalize_github_username_accepts_github_com() -> None:
    from resume_builder.build_resume import _normalize_github_username

    assert _normalize_github_username("https://github.com/jsmithpkp21") == "jsmithpkp21"


def test_ingest_job_context_linkedin_login_wall_falls_back_to_keywords(
    tmp_path: Path,
) -> None:
    """LinkedIn login-wall fixture: empty title/description; role from keywords param."""
    fixture = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "job_pages"
        / "linkedin_sdet_search_results.html"
    )
    import os

    env = os.environ.copy()
    env["RESUME_BUILDER_JOB_PAGE_FIXTURE"] = str(fixture)
    url = (
        "https://www.linkedin.com/jobs/search-results/?"
        "currentJobId=4380299765&keywords=SDET"
    )
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--outputs",
            "html,md",
            "--processing-mode",
            "raw",
            "--output-dir",
            str(tmp_path),
            "--job-url",
            url,
            "--company",
            "smoke",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    import json as _json

    snapshot = _json.loads(
        (tmp_path / "resumes" / "latest_resume_raw_ir_snapshot.json").read_text(
            encoding="utf-8"
        )
    )
    assert snapshot["job_context"]["source"] == "linkedin"
    assert snapshot["job_context"]["role_hint"] == "SDET"


def test_trim_for_role_ranks_and_reorders_by_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            """
            Job Title: Senior SDET
            Company: Charles Schwab
            Looking for a Senior SDET focused on debugging and CI reliability.
            """.strip()
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fake_scores(*, client: Any, resume: Any, experience: Any) -> dict[str, float]:
        del client, resume
        bullet_ids = [bullet.id for bullet in experience.bullets]
        if len(bullet_ids) < 5:
            return {bullet_id: 0.0 for bullet_id in bullet_ids}
        return {
            bullet_ids[0]: 0.10,
            bullet_ids[1]: 0.95,
            bullet_ids[2]: 0.20,
            bullet_ids[3]: 0.80,
            bullet_ids[4]: 0.70,
        }

    monkeypatch.setattr(
        "resume_builder.build_resume._score_bullet_relevance", fake_scores
    )

    trimmed = trim_for_role(resume)

    first_before = resume.experiences[0]
    first_after = trimmed.experiences[0]
    assert len(first_before.bullets) >= 5
    assert len(first_after.bullets) == len(first_before.bullets)

    # Highest-scored bullets should be reordered to the front; remaining bullets stay,
    # preserving stable order for ties/missing scores.
    assert [bullet.id for bullet in first_after.bullets[:5]] == [
        first_before.bullets[1].id,
        first_before.bullets[3].id,
        first_before.bullets[4].id,
        first_before.bullets[2].id,
        first_before.bullets[0].id,
    ]
    assert {bullet.id for bullet in first_after.bullets}.issubset(
        {bullet.id for bullet in first_before.bullets}
    )


def test_trim_for_role_logs_full_score_map_before_ranking(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    caplog.set_level(logging.DEBUG, logger="resume_builder.build_resume")

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            """
            Job Title: Senior SDET
            Company: Charles Schwab
            Looking for a Senior SDET focused on debugging and CI reliability.
            """.strip()
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fake_scores(*, client: Any, resume: Any, experience: Any) -> dict[str, float]:
        del client, resume
        return {
            bullet.id: (0.9 - (index * 0.1))
            for index, bullet in enumerate(experience.bullets)
        }

    monkeypatch.setattr(
        "resume_builder.build_resume._score_bullet_relevance", fake_scores
    )

    trim_for_role(resume)

    messages = [record.getMessage() for record in caplog.records]
    assert any("trim_for_role scores" in message for message in messages)
    first_exp = resume.experiences[0]
    assert any(first_exp.id in message for message in messages)
    assert any(first_exp.bullets[0].id in message for message in messages)


def test_trim_for_role_gracefully_falls_back_on_llm_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def raise_on_score(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, float]:
        del client, resume, experience
        raise RuntimeError("simulated llm failure")

    monkeypatch.setattr(
        "resume_builder.build_resume._score_bullet_relevance", raise_on_score
    )
    assert trim_for_role(resume) == resume


def test_trim_for_role_keeps_experience_when_scores_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def empty_scores(*, client: Any, resume: Any, experience: Any) -> dict[str, float]:
        del client, resume, experience
        return {}

    monkeypatch.setattr(
        "resume_builder.build_resume._score_bullet_relevance", empty_scores
    )

    trimmed = trim_for_role(resume)
    assert trimmed.experiences[0] == resume.experiences[0]


def test_trim_for_role_is_reproducible_in_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #22 acceptance: same input produces same selected bullet ids
    within a single Python process.

    The cross-process variant below additionally guards against
    hash-randomization-driven nondeterminism that this test cannot catch.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )

    def build() -> Any:
        return assemble_baseline_resume(
            profile=profile,
            target_role="Senior SDET",
            target_company="Charles Schwab",
            job_context=jd_ingest.ingest_job_text(
                "Job Title: Senior SDET\nCompany: Charles Schwab\n"
                "Looking for a Senior SDET focused on debugging and CI reliability."
            ),
            experiences=experiences,
            skills_by_category={},
        )

    def deterministic_scores(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, float]:
        del client, resume
        # Score from bullet id so ranking actually reorders bullets rather
        # than coincidentally returning them in their original input order.
        return {
            bullet.id: float(sum(ord(c) for c in bullet.id) % 100) / 100.0
            for bullet in experience.bullets
        }

    monkeypatch.setattr(
        "resume_builder.build_resume._score_bullet_relevance", deterministic_scores
    )

    first_ids = [
        [bullet.id for bullet in experience.bullets]
        for experience in trim_for_role(build()).experiences
    ]
    second_ids = [
        [bullet.id for bullet in experience.bullets]
        for experience in trim_for_role(build()).experiences
    ]
    assert sum(len(ids) for ids in first_ids) >= 5
    assert first_ids == second_ids


def test_trim_for_role_is_reproducible_across_processes(tmp_path: Path) -> None:
    """Issue #22 acceptance: same input produces same selected bullet ids
    across separate Python processes with different PYTHONHASHSEED values.

    Catches nondeterminism that only surfaces when hash-randomized dict/set
    iteration differs between processes — something the in-process test
    cannot detect.
    """
    experience_db = REPO_ROOT / "data" / "experience" / "experience_db.toml"
    runner = tmp_path / "repro_trim.py"
    runner.write_text(
        f"""import json
import os
import sys
from pathlib import Path

sys.path.insert(0, {str(REPO_ROOT)!r})
sys.path.insert(0, {str(REPO_ROOT / "src")!r})  # #41: resume_builder lives under src/
os.environ["RESUME_BUILDER_LLM_ENABLED"] = "1"

import resume_builder.build_resume as br
from resume_builder import jd_ingest


def _scores(*, client, resume, experience):
    return {{
        b.id: float(sum(ord(c) for c in b.id) % 100) / 100.0
        for b in experience.bullets
    }}


br._score_bullet_relevance = _scores

profile = br.load_profile(Path({str(PROFILE)!r}))
experiences = br.load_experiences(Path({str(experience_db)!r}))
resume = br.assemble_baseline_resume(
    profile=profile,
    target_role="Senior SDET",
    target_company="Charles Schwab",
    job_context=jd_ingest.ingest_job_text(
        "Job Title: Senior SDET\\nCompany: Charles Schwab\\n"
        "Looking for a Senior SDET focused on debugging and CI reliability."
    ),
    experiences=experiences,
    skills_by_category={{}},
)

trimmed = br.trim_for_role(resume)
print(json.dumps([[b.id for b in e.bullets] for e in trimmed.experiences]))
""",
        encoding="utf-8",
    )

    def run(seed: str) -> str:
        result = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    first = run("0")
    second = run("12345")
    assert first == second
    payload = json.loads(first)
    assert sum(len(ids) for ids in payload) >= 5


def test_enrich_data_adds_metadata_without_changing_bullets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fake_enrichment(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume
        first = experience.bullets[0]
        return {
            first.id: {
                "confidence": 0.91,
                "tags": ["sdet", "automation"],
            }
        }

    monkeypatch.setattr(
        "resume_builder.build_resume._enrich_experience_bullets", fake_enrichment
    )

    enriched = enrich_data(resume)
    assert enriched.experiences == resume.experiences
    assert enriched.enrichment_by_bullet_id
    sample = next(iter(enriched.enrichment_by_bullet_id.values()))
    assert sample["confidence"] == 0.91
    assert sample["tags"] == ["sdet", "automation"]


def test_enrich_data_gracefully_falls_back_on_llm_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def raise_on_enrich(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume, experience
        raise RuntimeError("simulated llm failure")

    monkeypatch.setattr(
        "resume_builder.build_resume._enrich_experience_bullets", raise_on_enrich
    )
    assert enrich_data(resume) == resume


def test_trim_by_rules_limits_action_word_repetition() -> None:
    profile = load_profile(PROFILE)
    experiences = (
        Experience(
            id="exp-1",
            job_title="Role 1",
            company="Contoso",
            start_date="2024-01",
            end_date="2025-01",
            general_role_description="Did role 1",
            related_skills=("Python",),
            bullets=(
                Bullet(
                    id="b1",
                    text="Designed framework architecture for shared automation.",
                    skills=("Python",),
                    impact_type="architecture",
                    domain="automation",
                ),
                Bullet(
                    id="b2",
                    text="Designed reusable orchestration layer for tests.",
                    skills=("Python",),
                    impact_type="architecture",
                    domain="automation",
                ),
                Bullet(
                    id="b3",
                    text="Built debugging tools for flaky failures.",
                    skills=("Python",),
                    impact_type="quality",
                    domain="tooling",
                ),
                Bullet(
                    id="b5",
                    text="Implemented structured test coverage tracking.",
                    skills=("Python",),
                    impact_type="delivery-speed",
                    domain="automation",
                ),
            ),
        ),
        Experience(
            id="exp-2",
            job_title="Role 2",
            company="Contoso",
            start_date="2023-01",
            end_date="2024-01",
            general_role_description="Did role 2",
            related_skills=("Python",),
            bullets=(
                Bullet(
                    id="b4",
                    text="Designed remote lab workflows for validation.",
                    skills=("Python",),
                    impact_type="quality",
                    domain="lab",
                ),
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )
    resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "b1": {"confidence": 0.10, "tags": ["architecture"]},
            "b2": {"confidence": 0.90, "tags": ["architecture"]},
            "b3": {"confidence": 0.80, "tags": ["debugging"]},
            "b4": {"confidence": 0.05, "tags": ["lab"]},
            "b5": {"confidence": 0.70, "tags": ["delivery"]},
        },
    )

    trimmed = trim_by_rules(resume)

    assert [bullet.id for bullet in trimmed.experiences[0].bullets] == [
        "b2",
        "b3",
        "b5",
    ]
    assert [bullet.id for bullet in trimmed.experiences[1].bullets] == ["b4"]
    designed_count = sum(
        1
        for experience in trimmed.experiences
        for bullet in experience.bullets
        if bullet.text.startswith("Designed")
    )
    assert designed_count == 2


def test_trim_by_rules_line_budget_keeps_all_within_budget() -> None:
    profile = load_profile(PROFILE)
    experiences: list[Experience] = []
    enrichment_by_bullet_id: dict[str, dict[str, object]] = {}
    action_words = [
        "Built",
        "Created",
        "Implemented",
        "Improved",
        "Optimized",
        "Delivered",
        "Automated",
        "Integrated",
        "Streamlined",
        "Strengthened",
        "Expanded",
        "Advanced",
        "Launched",
        "Enabled",
        "Stabilized",
        "Refined",
        "Orchestrated",
        "Directed",
        "Modernized",
        "Scaled",
        "Accelerated",
        "Reduced",
        "Elevated",
        "Simplified",
    ]
    for exp_index in range(6):
        bullets: list[Bullet] = []
        for bullet_index in range(4):
            bullet_id = f"exp{exp_index}-b{bullet_index}"
            action_word = action_words[exp_index * 4 + bullet_index]
            bullets.append(
                Bullet(
                    id=bullet_id,
                    text=f"{action_word} measurable automation impact for shared tooling.",
                    skills=("Python",),
                    impact_type="quality",
                    domain="automation",
                )
            )
            enrichment_by_bullet_id[bullet_id] = {
                "confidence": (exp_index * 10 + bullet_index) / 100,
                "tags": ["automation"],
            }
        experiences.append(
            Experience(
                id=f"exp-{exp_index}",
                job_title=f"Role {exp_index}",
                company="Contoso",
                start_date="2024-01",
                end_date="2025-01",
                general_role_description="Did role work",
                related_skills=("Python",),
                bullets=tuple(bullets),
            )
        )

    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=tuple(experiences),
        skills_by_category={},
    )
    resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id=enrichment_by_bullet_id,
    )

    trimmed = trim_by_rules(resume)

    # No fixed total bullet cap: line-budget trimming keeps all bullets whose
    # estimated line count fits within DEFAULT_MAX_BULLET_LINES. When all content
    # fits the budget, every bullet is retained.
    assert sum(len(experience.bullets) for experience in trimmed.experiences) == 24
    assert all(len(experience.bullets) >= 2 for experience in trimmed.experiences)
    assert len(trimmed.experiences[0].bullets) == 4


def test_trim_by_rules_line_budget_removes_low_confidence_bullets_over_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_MAX_BULLET_LINES", 4)

    profile = load_profile(PROFILE)
    exp_one = Experience(
        id="exp-one",
        job_title="Role One",
        company="Company",
        start_date="2020-01",
        end_date="2021-01",
        general_role_description="Role one summary.",
        related_skills=(),
        bullets=(
            Bullet(
                "one-high", "Built stable systems.", ("Python",), "impact", "domain"
            ),
            Bullet(
                "one-mid", "Improved test diagnostics.", ("Pytest",), "impact", "domain"
            ),
            Bullet("one-low", "Documented edge cases.", ("Docs",), "impact", "domain"),
        ),
    )
    exp_two = Experience(
        id="exp-two",
        job_title="Role Two",
        company="Company",
        start_date="2021-02",
        end_date="2022-02",
        general_role_description="Role two summary.",
        related_skills=(),
        bullets=(
            Bullet(
                "two-high",
                "Automated core validation.",
                ("Automation",),
                "impact",
                "domain",
            ),
            Bullet(
                "two-mid",
                "Expanded regression coverage.",
                ("Testing",),
                "impact",
                "domain",
            ),
            Bullet(
                "two-low",
                "Tracked manual follow-up items.",
                ("Analysis",),
                "impact",
                "domain",
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(exp_one, exp_two),
        skills_by_category={},
    )
    resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "one-high": {"confidence": 0.9},
            "one-mid": {"confidence": 0.8},
            "one-low": {"confidence": 0.1},
            "two-high": {"confidence": 0.95},
            "two-mid": {"confidence": 0.7},
            "two-low": {"confidence": 0.2},
        },
    )

    trimmed = trim_by_rules(resume)

    assert [bullet.id for bullet in trimmed.experiences[0].bullets] == [
        "one-high",
        "one-mid",
    ]
    assert [bullet.id for bullet in trimmed.experiences[1].bullets] == [
        "two-high",
        "two-mid",
    ]
    assert all(len(experience.bullets) >= 2 for experience in trimmed.experiences)


def _make_minimal_budget_profile() -> build_resume.Profile:
    """Return a deterministic Profile for bullet-line budget tests.
    Using a fixed inline Profile instead of load_profile(PROFILE) avoids
    non-determinism from per-contributor profile.toml content.
    """
    return build_resume.Profile(
        name="Budget Test Person",
        headline="Staff Test Architect",
        location="Austin, TX",
        email="budget-test@example.com",
        phone="555-0199",
        website="example.com",
        linkedin="linkedin.com/in/budget-test",
        github="github.com/budget-test",
        summary="Drives test architecture across teams.",
        education_entries=(),
        leadership_community_entries=(),
    )


def test_compute_bullet_line_budget_drops_when_non_bullet_layout_pressure_is_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force a tiny page budget so non-bullet pressure dominates and the bullet
    # ceiling drops below the absolute hard ceiling.
    monkeypatch.setattr(build_resume, "DEFAULT_TWO_PAGE_PT_BUDGET", 440)

    profile = _make_minimal_budget_profile()
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Staff Test Architect",
        target_company="Graphcore",
        job_context=None,
        experiences=load_experiences(
            REPO_ROOT / "data" / "experience" / "experience_db.toml"
        ),
        skills_by_category={
            "Automation Architecture & Quality": [
                "Capability-Driven Design",
                "Distributed Execution",
                "Model-Agnostic Abstractions",
                "Reusable Components",
                "Playwright",
                "Pytest",
            ],
            "Platform CI/CD & Infrastructure": [
                "CI/CD",
                "GitHub Actions",
                "Docker",
                "Dependency Management",
            ],
        },
    )

    budget = build_resume._compute_bullet_line_budget(resume)

    assert budget < build_resume.DEFAULT_MAX_BULLET_LINES
    assert budget >= 1


def test_compute_bullet_line_budget_respects_hard_ceiling_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_MAX_BULLET_LINES", 7)
    monkeypatch.setattr(build_resume, "DEFAULT_TWO_PAGE_PT_BUDGET", 4400)

    profile = _make_minimal_budget_profile()
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=load_experiences(
            REPO_ROOT / "data" / "experience" / "experience_db.toml"
        ),
        skills_by_category={},
    )

    assert build_resume._compute_bullet_line_budget(resume) == 7


def test_compute_bullet_line_budget_matches_processed_html_header_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_MAX_BULLET_LINES", 99)
    # Sized so this fixture's non_bullet_pt leaves exactly 7 bullet lines of
    # remaining budget at PDF_BULLET_LINE_PT (12pt). non_bullet_pt for the
    # fixture: 15.2 (h1) + 22 (contact+linkedin) + 16 (header divider) + 13
    # (title) + 66 (summary block reserved at PROFILE_SUMMARY_MAX_LINES=6 *
    # 11pt) + 42 (h2 x 2: Key Skills + Professional Experience) + 143
    # (skills section reserved at TARGET_LINES_MAX=13 * 11pt) + 65.4 (1
    # grouped company-line block, 2 h3s, 2 body role-summaries capped at
    # SUMMARY_MAX_LINES=2) = 382.6pt. 470 - 382.6 = 87.4; 87.4 // 12 = 7.
    monkeypatch.setattr(build_resume, "DEFAULT_TWO_PAGE_PT_BUDGET", 470)
    monkeypatch.setattr(
        build_resume, "_estimate_wrapped_line_count", lambda *_args, **_kwargs: 1
    )
    monkeypatch.setattr(
        build_resume, "_estimate_minimum_required_bullet_lines", lambda _experiences: 1
    )

    profile = build_resume.Profile(
        name="Test Person",
        headline="Staff Test Architect",
        location="Austin, TX",
        email="test@example.com",
        phone="555-0100",
        website="example.com",
        linkedin="linkedin.com/in/test",
        github="github.com/test",
        summary="Drives automation architecture across teams.",
        education_entries=(),
        leadership_community_entries=(),
    )
    experiences = (
        Experience(
            id="budget-hp-1",
            job_title="Architect, Python Test Framework",
            company="HP / Poly",
            start_date="2024-01",
            end_date="2025-01",
            general_role_description="Led framework modernization.",
            related_skills=("Python", "Pytest", "Playwright"),
            bullets=(),
        ),
        Experience(
            id="budget-hp-2",
            job_title="Technical Advisor / SDET",
            company="Polycom",
            start_date="2023-01",
            end_date="2024-01",
            general_role_description="Guided multi-team adoption.",
            related_skills=("CI/CD", "Leadership"),
            bullets=(),
        ),
    )
    resume = build_resume.ResumeIR(
        profile=profile,
        target_role="",
        target_company="",
        display_headline=profile.headline,
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    # Processed HTML renders summary as a paragraph, one company-line per grouped
    # company block, one job-title-line per role, and hides related-skills lines.
    assert build_resume._compute_bullet_line_budget(resume) == 7


def test_summarize_for_role_generates_distinct_summaries() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior Software Engineer in Test",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior Software Engineer in Test\n"
            "Company: Charles Schwab\n"
            "Need Python-based automation and CI quality ownership."
        ),
        experiences=experiences,
        skills_by_category={},
    )

    summarized = summarize_for_role(resume)
    changed = [
        (before, after)
        for before, after in zip(
            resume.experiences, summarized.experiences, strict=True
        )
        if before.general_role_description != after.general_role_description
    ]
    assert changed

    for _before, after in changed:
        summary = after.general_role_description
        assert summary.strip()
        for bullet in after.bullets:
            assert summary.strip().lower() != bullet.text.strip().lower()
            assert summary.strip().lower() not in bullet.text.strip().lower()
        assert "Focused on" not in summary
        assert "Aligned execution" not in summary


def test_summarize_for_role_enforces_two_line_layout_without_single_word_wraps() -> (
    None
):
    profile = load_profile(PROFILE)
    experiences = (
        Experience(
            id="exp-layout",
            job_title="Lead Automation Engineer",
            company="Contoso",
            start_date="2024-01",
            end_date="2025-01",
            general_role_description=(
                "Led a broad automation modernization program spanning multiple products, "
                "delivery organizations, and infrastructure dependencies."
            ),
            related_skills=("Python", "Pytest", "Playwright", "CI/CD"),
            bullets=(
                Bullet(
                    id="layout-b1",
                    text=(
                        "Implemented deterministic orchestration patterns for long-running "
                        "cross-platform validation workflows."
                    ),
                    skills=("Python", "Pytest"),
                    impact_type="quality",
                    domain="automation",
                ),
                Bullet(
                    id="layout-b2",
                    text=(
                        "Integrated resilient pipeline guardrails and telemetry dashboards "
                        "to reduce flaky failures."
                    ),
                    skills=("CI/CD", "Logging"),
                    impact_type="quality",
                    domain="ci",
                ),
                Bullet(
                    id="layout-b3",
                    text=(
                        "Expanded framework support for service-layer testing and UI flows "
                        "with reusable harnesses."
                    ),
                    skills=("Playwright", "Python"),
                    impact_type="architecture",
                    domain="automation",
                ),
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Staff Test Automation Engineer",
        target_company="",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Staff Test Automation Engineer\n"
            "Need strong Python, CI ownership, and cross-functional reliability leadership."
        ),
        experiences=experiences,
        skills_by_category={},
    )

    summarized = summarize_for_role(resume)
    summary = summarized.experiences[0].general_role_description
    wrapped_lines = _summary_wrap_lines(summary)
    assert 1 <= len(wrapped_lines) <= 2
    assert all(len(line.split()) >= 2 for line in wrapped_lines[1:])


def test_summarize_for_role_avoids_fragmented_connector_sentences() -> None:
    profile = load_profile(PROFILE)
    experiences = (
        Experience(
            id="exp-fragment",
            job_title="Senior Test Automation Engineer",
            company="Contoso",
            start_date="2024-01",
            end_date="2025-01",
            general_role_description=(
                "Led platform reliability automation across mobile and web release trains "
                "using Python and to"
            ),
            related_skills=("Python", "ADB", "CI/CD"),
            bullets=(
                Bullet(
                    id="frag-b1",
                    text="Built deterministic mobile and API automation coverage across release trains.",
                    skills=("Python", "ADB"),
                    impact_type="quality",
                    domain="automation",
                ),
                Bullet(
                    id="frag-b2",
                    text="Integrated CI quality gates and reliability diagnostics for regression triage.",
                    skills=("CI/CD", "Logging"),
                    impact_type="quality",
                    domain="ci",
                ),
                Bullet(
                    id="frag-b3",
                    text="Stabilized flaky workflows by instrumenting debug traces and failure classification.",
                    skills=("Python", "Pytest"),
                    impact_type="quality",
                    domain="debugging",
                ),
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior Software Engineer in Test",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior Software Engineer in Test\n"
            "Need Python and ADB automation plus CI quality ownership."
        ),
        experiences=experiences,
        skills_by_category={},
    )

    summarized = summarize_for_role(resume)
    summary = summarized.experiences[0].general_role_description

    assert summary.strip()
    assert " to. Focused" not in summary
    assert not summary.endswith(" to.")
    assert not summary.endswith(" Focused.")


def test_summarize_for_role_uses_no_boilerplate_alignment_phrases() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=jd_ingest.ingest_job_text("Job Title: Senior SDET"),
        experiences=experiences,
        skills_by_category={"Testing": ["Python", "Pytest"]},
    )

    summarized = summarize_for_role(resume)
    for exp in summarized.experiences:
        assert "Focused on" not in exp.general_role_description
        assert "Aligned execution" not in exp.general_role_description


def test_fit_summary_layout_drops_dangling_fragment_tail_words() -> None:
    fitted = build_resume._fit_summary_layout(
        "Led quality modernization across distributed systems. Focused on Python and ADB to"
    )

    assert fitted
    assert not fitted.endswith(" to.")
    assert not fitted.endswith(" Focused.")


def test_summarize_for_role_avoids_clipped_clause_tail_fragments() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=jd_ingest.ingest_job_text("Job Title: Senior SDET"),
        experiences=experiences,
        skills_by_category={"Testing": ["Python", "Pytest"]},
    )

    summarized = summarize_for_role(resume)
    summaries_by_title = {
        exp.job_title: exp.general_role_description for exp in summarized.experiences
    }

    assert (
        " into a shared."
        not in summaries_by_title["Technical Lead, Corporate Framework Integration"]
    )
    assert (
        " initiative, shaping."
        not in summaries_by_title[
            "Lead Technical Designer, Corporate Automation Initiative"
        ]
    )
    assert summaries_by_title["Technical Advisor / SDET, Headset Team"].endswith(
        "framework."
    )


def test_summarize_profile_for_role_generates_role_aware_top_summary() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\n"
            "Company: Charles Schwab\n"
            "Need Python-based automation and CI quality ownership."
        ),
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summarized = summarize_profile_for_role(resume)

    assert summarized.profile.summary != profile.summary
    assert PROFILE_PRIMARY_ROLE in summarized.profile.summary
    expected_role_label = build_resume._summary_role_label_from_title(resume)
    assert summarized.profile.summary.startswith(
        f"{expected_role_label} delivering automation framework architecture"
    )
    assert (
        "across Video, Audio, and Headset product teams." in summarized.profile.summary
    )
    assert "Senior SDET" not in summarized.profile.summary
    assert "Charles Schwab" not in summarized.profile.summary
    assert "Python" in summarized.profile.summary


def test_summarize_profile_for_role_avoids_clipped_sentence_tail_fragments() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Graphcore",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\n"
            "Company: Graphcore\n"
            "Need Python and CI quality ownership."
        ),
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summarized = summarize_profile_for_role(resume)

    assert "new Python test." not in summarized.profile.summary
    assert summarized.profile.summary.endswith((".", "!", "?"))


def test_summarize_profile_for_role_avoids_generic_specializing_phrase() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summarized = summarize_profile_for_role(resume)

    assert f"specializing in {PROFILE_PRIMARY_ROLE}" not in summarized.profile.summary
    assert PROFILE_PRIMARY_ROLE in summarized.profile.summary
    assert "Target role:" not in summarized.profile.summary
    assert "Key skills:" not in summarized.profile.summary


def test_summarize_profile_for_role_is_identity_when_summary_unchanged() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    role = "Senior SDET"
    seed_resume = assemble_baseline_resume(
        profile=profile,
        target_role=role,
        target_company="",
        job_context=jd_ingest.ingest_job_text("Job Title: Senior SDET"),
        experiences=experiences,
        skills_by_category={},
    )
    expected_summary = summarize_profile_for_role(seed_resume).profile.summary
    profile_with_expected = type(profile)(
        name=profile.name,
        headline=profile.headline,
        location=profile.location,
        email=profile.email,
        phone=profile.phone,
        website=profile.website,
        linkedin=profile.linkedin,
        github=profile.github,
        summary=expected_summary,
        education_entries=profile.education_entries,
        leadership_community_entries=profile.leadership_community_entries,
    )
    resume = assemble_baseline_resume(
        profile=profile_with_expected,
        target_role=role,
        target_company="",
        job_context=jd_ingest.ingest_job_text("Job Title: Senior SDET"),
        experiences=experiences,
        skills_by_category={},
    )

    assert summarize_profile_for_role(resume) is resume


def test_summarize_profile_for_role_enforces_layout_and_max_word_constraints() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summarized = summarize_profile_for_role(resume)
    word_count = len(summarized.profile.summary.split())
    assert word_count <= PROFILE_SUMMARY_MAX_WORDS
    wrapped_lines = _summary_wrap_lines(
        summarized.profile.summary,
        line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH,
    )
    assert len(wrapped_lines) <= PROFILE_SUMMARY_MAX_LINES


def test_summarize_profile_for_role_respects_six_line_layout_cap() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\n"
            "Company: Charles Schwab\n"
            "Need Python and CI quality ownership."
        ),
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summarized = summarize_profile_for_role(resume)
    wrapped_lines = _summary_wrap_lines(
        summarized.profile.summary,
        line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH,
    )
    assert len(wrapped_lines) <= PROFILE_SUMMARY_MAX_LINES


def test_expand_profile_summary_to_min_words_rotates_sparse_fragments() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={"Testing": ["Python", "Pytest"]},
    )

    candidate = "Senior SDET with strengths in Python."
    min_words = 14
    result = build_resume._expand_profile_summary_to_min_words(
        candidate,
        resume,
        min_words,
        fragments=["Improved test reliability through deterministic checks."],
    )

    assert len(result.split()) >= min_words


def test_expand_profile_summary_to_min_words_uses_skill_fallback_without_fragments() -> (
    None
):
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={"Testing": ["Python"]},
    )

    candidate = "Senior SDET with strengths in Python."
    min_words = 12
    result = build_resume._expand_profile_summary_to_min_words(
        candidate,
        resume,
        min_words,
        fragments=[],
    )

    assert len(result.split()) >= min_words
    assert "Focus includes" in result


# ---------------------------------------------------------------------------
# transform_for_role tests
# ---------------------------------------------------------------------------


def test_expand_profile_summary_to_min_words_does_not_leak_target_role_on_empty_data() -> (
    None
):
    profile = load_profile(PROFILE)
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Graphcore Senior Principal Test Framework Software Engineer",
        target_company="Graphcore",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Graphcore Senior Principal Test Framework Software Engineer\nCompany: Graphcore"
        ),
        experiences=(),
        skills_by_category={},
    )
    candidate = "Software Engineer with strengths in automation."
    result = build_resume._expand_profile_summary_to_min_words(
        candidate,
        resume,
        min_words=12,
        fragments=[],
    )
    assert "Focus includes" in result
    assert "graphcore" not in result.lower()


def test_summarize_profile_for_role_truncates_summary_at_max_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify truncation respects max_words ceiling.

    Sentence-boundary preservation means the result may fall below the configured
    minimum-word floor (PROFILE_SUMMARY_MIN_RATIO) when incomplete trailing clauses
    are dropped.  The hard constraints are: (a) at most max_words words, (b) ends
    with terminal punctuation, and (c) no double-punctuation artefact.
    """
    max_words = 20
    monkeypatch.setattr(
        "resume_builder.build_resume.PROFILE_SUMMARY_MAX_WORDS", max_words
    )
    monkeypatch.setattr(
        "resume_builder.build_resume.PROFILE_SUMMARY_MIN_RATIO",
        PROFILE_SUMMARY_MIN_RATIO,
    )

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={
            "Testing": [
                "enterprise test automation framework architecture",
                "distributed reliability engineering and quality gates",
                "cross-platform UI API and service-layer diagnostics",
            ]
        },
    )
    result = summarize_profile_for_role(resume)
    summary_words = result.profile.summary.split()

    # Summary may naturally fit below nominal minimum after sentence-boundary
    # preservation drops incomplete trailing clauses.
    assert len(summary_words) >= 1
    assert len(summary_words) <= max_words, (
        f"Summary has {len(summary_words)} words, max is {max_words}"
    )
    assert result.profile.summary.endswith("."), (
        f"Summary should end with period, got: {result.profile.summary[-10:]}"
    )
    assert not result.profile.summary.endswith(".."), (
        f"Summary should not have double punctuation: {result.profile.summary[-10:]}"
    )


def test_generate_profile_summary_avoids_double_punctuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify truncation keeps single terminal punctuation when a token already has it."""
    max_words = 15
    monkeypatch.setattr(
        "resume_builder.build_resume.PROFILE_SUMMARY_MAX_WORDS", max_words
    )

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    long_skills = {
        "Category": [
            "large-scale UI API and service-layer reliability engineering",
            "deterministic CI quality-gate architecture with deep diagnostics",
            "cross-platform framework design for enterprise automation delivery",
        ]
    }
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category=long_skills,
    )
    result = summarize_profile_for_role(resume)

    # Word count must not exceed the cap; the exact count depends on profile content
    # (per-contributor profile.toml can vary the opening fragment length).
    assert len(result.profile.summary.split()) <= max_words, (
        f"Summary exceeds max_words={max_words}: {result.profile.summary!r}"
    )
    assert result.profile.summary.endswith("."), result.profile.summary
    assert ".." not in result.profile.summary, (
        f"Found double period in summary: {result.profile.summary}"
    )


def test_generate_profile_summary_clamps_min_words_to_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("resume_builder.build_resume.PROFILE_SUMMARY_MAX_WORDS", 10)
    monkeypatch.setattr("resume_builder.build_resume.PROFILE_SUMMARY_MIN_RATIO", 1.5)

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    result = summarize_profile_for_role(resume)
    # max is a ceiling; exact count varies with profile content (local headlines differ).
    assert len(result.profile.summary.split()) <= 10


def test_transform_for_role_is_identity_without_job_context() -> None:
    """transform_for_role returns the same IR when no job context is provided."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )
    assert transform_for_role(resume) is resume


def test_transform_for_role_is_identity_when_llm_disabled() -> None:
    """transform_for_role returns the same IR when neither LLM nor fixture is enabled."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )
    # Neither RESUME_BUILDER_LLM_ENABLED nor RESUME_BUILDER_LLM_FIXTURE are set.
    assert transform_for_role(resume) is resume


def _assert_llm_stage_skips_empty_job_context_signals(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stage: Callable[[build_resume.ResumeIR], build_resume.ResumeIR],
    stage_name: str,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=jd_ingest.JobContext(
            input_url="https://example.com/jobs/123",
            normalized_url="https://example.com/jobs/123",
            source="company-site",
            role_hint="",
            company_name="",
            job_id="123",
            fetch_status="fetch_failed",
            page_title="",
            description_excerpt="",
            notes=(),
            company_research=None,
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(f"{stage_name} should not initialize LLMClient")

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env", fail_if_called
    )

    result = stage(resume)

    assert result is resume
    assert result.experiences == resume.experiences
    assert result.enrichment_by_bullet_id == resume.enrichment_by_bullet_id


def test_transform_for_role_skips_empty_job_context_signals_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_llm_stage_skips_empty_job_context_signals(
        monkeypatch,
        stage=transform_for_role,
        stage_name="transform_for_role",
    )


def test_trim_for_role_skips_empty_job_context_signals_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_llm_stage_skips_empty_job_context_signals(
        monkeypatch,
        stage=trim_for_role,
        stage_name="trim_for_role",
    )


def test_enrich_data_skips_empty_job_context_signals_even_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_llm_stage_skips_empty_job_context_signals(
        monkeypatch,
        stage=enrich_data,
        stage_name="enrich_data",
    )


def test_enrich_data_runs_when_target_role_signal_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="",
        job_context=jd_ingest.JobContext(
            input_url="https://example.com/jobs/123",
            normalized_url="https://example.com/jobs/123",
            source="company-site",
            role_hint="",
            company_name="",
            job_id="123",
            fetch_status="fetch_failed",
            page_title="",
            description_excerpt="",
            notes=(),
            company_research=None,
        ),
        experiences=experiences,
        skills_by_category={},
    )

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env",
        lambda *_args, **_kwargs: object(),
    )

    first_bullet_id = resume.experiences[0].bullets[0].id

    def fake_enrich(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume, experience
        return {first_bullet_id: {"confidence": 0.88, "tags": ["sdet"]}}

    monkeypatch.setattr(
        "resume_builder.build_resume._enrich_experience_bullets", fake_enrich
    )

    enriched = enrich_data(resume)

    assert enriched is not resume
    assert enriched.experiences == resume.experiences
    assert enriched.enrichment_by_bullet_id[first_bullet_id]["confidence"] == 0.88


def test_enrich_data_runs_when_job_context_role_hint_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=jd_ingest.JobContext(
            input_url="https://example.com/jobs/123",
            normalized_url="https://example.com/jobs/123",
            source="company-site",
            role_hint="Senior SDET",
            company_name="",
            job_id="123",
            fetch_status="fetch_failed",
            page_title="",
            description_excerpt="",
            notes=(),
            company_research=None,
        ),
        experiences=experiences,
        skills_by_category={},
    )

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env",
        lambda *_args, **_kwargs: object(),
    )

    first_bullet_id = resume.experiences[0].bullets[0].id

    def fake_enrich(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume, experience
        return {first_bullet_id: {"confidence": 0.77, "tags": ["sdet"]}}

    monkeypatch.setattr(
        "resume_builder.build_resume._enrich_experience_bullets", fake_enrich
    )

    enriched = enrich_data(resume)

    assert enriched is not resume
    assert enriched.experiences == resume.experiences
    assert enriched.enrichment_by_bullet_id[first_bullet_id]["confidence"] == 0.77


def test_transform_for_role_rewrites_bullet_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transform_for_role updates bullet text when the LLM returns a non-empty rewrite."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    first_bullet_id = resume.experiences[0].bullets[0].id
    rewritten_text = (
        "Built a lightweight abstraction layer from an inherited ADB/UI Automator "
        "test flow, enabling Android-based embedded UI testing across PolyOS, "
        "Zoom, Teams, and Google Meet."
    )

    def fake_rewrite(*, client: Any, resume: Any, experience: Any) -> dict[str, str]:
        del client, resume, experience
        return {first_bullet_id: rewritten_text}

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", fake_rewrite
    )

    transformed = transform_for_role(resume)

    first_original = resume.experiences[0].bullets[0]
    first_transformed = transformed.experiences[0].bullets[0]
    assert first_transformed.id == first_original.id
    assert first_transformed.text == rewritten_text
    assert first_transformed.text != first_original.text


def test_transform_for_role_preserves_bullet_count_and_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transform_for_role does not add, remove, or reorder bullets."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fake_rewrite(*, client: Any, resume: Any, experience: Any) -> dict[str, str]:
        del client, resume
        # Rewrite every bullet with a prefix to ensure all get new text.
        return {bullet.id: f"Reframed: {bullet.text}" for bullet in experience.bullets}

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", fake_rewrite
    )

    transformed = transform_for_role(resume)

    for original_exp, transformed_exp in zip(
        resume.experiences, transformed.experiences, strict=True
    ):
        assert len(transformed_exp.bullets) == len(original_exp.bullets)
        for orig_b, trans_b in zip(
            original_exp.bullets, transformed_exp.bullets, strict=True
        ):
            assert trans_b.id == orig_b.id
            assert trans_b.skills == orig_b.skills
            assert trans_b.impact_type == orig_b.impact_type
            assert trans_b.domain == orig_b.domain


def test_transform_for_role_keeps_original_when_rewrite_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transform_for_role leaves bullet text unchanged when the rewrite is blank."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def fake_rewrite_empty(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, str]:
        del client, resume
        # Return empty strings for all bullets — should be treated as no rewrite.
        return {bullet.id: "   " for bullet in experience.bullets}

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", fake_rewrite_empty
    )

    transformed = transform_for_role(resume)

    for original_exp, transformed_exp in zip(
        resume.experiences, transformed.experiences, strict=True
    ):
        for orig_b, trans_b in zip(
            original_exp.bullets, transformed_exp.bullets, strict=True
        ):
            assert trans_b.text == orig_b.text


def test_transform_for_role_gracefully_falls_back_on_llm_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """transform_for_role returns the original IR when the inner rewrite call raises."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    def raise_on_rewrite(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, str]:
        del client, resume, experience
        raise RuntimeError("simulated llm failure")

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", raise_on_rewrite
    )
    assert transform_for_role(resume) == resume


def test_transform_for_role_normalizes_sentence_start_casing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lowercase first-letter rewrites are normalized to sentence case."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    first_bullet = resume.experiences[0].bullets[0]
    lowered = first_bullet.text[0].lower() + first_bullet.text[1:]

    def fake_rewrite(*, client: Any, resume: Any, experience: Any) -> dict[str, str]:
        del client, resume, experience
        return {first_bullet.id: lowered}

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", fake_rewrite
    )

    transformed = transform_for_role(resume)
    rewritten = transformed.experiences[0].bullets[0].text
    assert rewritten[0].isupper()
    assert rewritten == first_bullet.text


def test_transform_for_role_rejects_generic_hype_rewrites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guardrails reject over-generic hype phrasing and keep canonical text."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET",
        target_company="Charles Schwab",
        job_context=jd_ingest.ingest_job_text(
            "Job Title: Senior SDET\nCompany: Charles Schwab"
        ),
        experiences=experiences,
        skills_by_category={},
    )

    first_bullet = resume.experiences[0].bullets[0]
    hype = "Demonstrated strong leadership skills across dynamic projects."

    def fake_rewrite(*, client: Any, resume: Any, experience: Any) -> dict[str, str]:
        del client, resume, experience
        return {first_bullet.id: hype}

    monkeypatch.setattr(
        "resume_builder.build_resume._rewrite_experience_bullets", fake_rewrite
    )

    transformed = transform_for_role(resume)
    assert transformed.experiences[0].bullets[0].text == first_bullet.text


def test_get_base_role_uses_target_role_first() -> None:
    """_get_base_role prefers target_role over all other sources."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Software Test Engineer | Python",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    # Should extract only the base part (before |)
    assert _get_base_role(resume) == "Software Test Engineer"


def test_get_base_role_extracts_before_pipe() -> None:
    """_get_base_role correctly handles pipe-separated target roles."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior SDET | Framework Architect",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    assert _get_base_role(resume) == "Senior SDET"


def test_get_base_role_falls_back_to_display_headline() -> None:
    """_get_base_role falls back to display_headline when target_role is empty."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    base_resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )
    resume = type(base_resume)(
        profile=base_resume.profile,
        target_role="",  # Empty target_role
        target_company=base_resume.target_company,
        display_headline="Lead Automation Engineer | Framework",
        job_context=base_resume.job_context,
        experiences=base_resume.experiences,
        skills_by_category=base_resume.skills_by_category,
        enrichment_by_bullet_id=base_resume.enrichment_by_bullet_id,
    )

    assert _get_base_role(resume) == "Lead Automation Engineer"


def test_get_base_role_normalizes_whitespace() -> None:
    """_get_base_role normalizes internal whitespace."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Senior  SDET  Engineer",  # Extra spaces
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    assert _get_base_role(resume) == "Senior SDET Engineer"


def test_generate_profile_summary_omits_target_role_tokens() -> None:
    """Profile summary should not leak target-role tokens into visible text."""
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="SDET",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    summary = build_resume.summarize_profile_for_role(resume).profile.summary
    assert "core strengths include" in summary.lower()
    assert "Graphcore" not in summary
    assert "sdet" not in summary.lower()


def test_collect_profile_scope_labels_returns_deterministic_order() -> None:
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    labels = build_resume._collect_profile_scope_labels(experiences)
    assert labels[:3] == ["Video", "Audio", "Headset"]


def test_summary_role_label_preserves_hyphenated_role_words() -> None:
    profile = load_profile(_TRACKED_PROFILE_PATH)
    custom_profile = type(profile)(
        name=profile.name,
        headline="Full-stack Engineer / Test Automation",
        location=profile.location,
        email=profile.email,
        phone=profile.phone,
        website=profile.website,
        linkedin=profile.linkedin,
        github=profile.github,
        summary=profile.summary,
        education_entries=profile.education_entries,
        leadership_community_entries=profile.leadership_community_entries,
    )
    resume = build_resume.ResumeIR(
        profile=custom_profile,
        target_role="",
        target_company="",
        display_headline=custom_profile.headline,
        job_context=None,
        experiences=(),
        skills_by_category={},
    )
    assert build_resume._summary_role_label_from_title(resume) == "Full-stack Engineer"


def test_generate_profile_summary_does_not_repeat_full_resume_title() -> None:
    profile = load_profile(_TRACKED_PROFILE_PATH)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={"Testing": ["Python", "Pytest", "Playwright"]},
    )

    summary = build_resume.summarize_profile_for_role(resume).profile.summary
    assert derive_resume_title(resume) not in summary


def test_generate_profile_summary_avoids_meta_labels_and_duplicate_sentences() -> None:
    profile = load_profile(PROFILE)
    experiences = load_experiences(
        REPO_ROOT / "data" / "experience" / "experience_db.toml"
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="Software Engineer",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={
            "Testing": ["Python", "Pytest", "Playwright"],
        },
    )

    summary = build_resume.summarize_profile_for_role(resume).profile.summary

    assert "Target role:" not in summary
    assert "Key skills:" not in summary
    assert (
        summary.count(
            "Led technical evaluation and design discussions for integrating multiple product groups"
        )
        <= 1
    )


def test_trim_by_rules_enforces_line_budget_with_overlong_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_MAX_BULLET_LINES", 4)
    profile = load_profile(PROFILE)
    long_token = "x" * (build_resume.DEFAULT_BULLET_LINE_WIDTH + 40)
    exp = Experience(
        id="exp-overlong",
        job_title="Senior SDET",
        company="Contoso",
        start_date="2020-01",
        end_date="2024-01",
        general_role_description="Role summary",
        related_skills=("Python",),
        bullets=(
            Bullet(
                "keep-1",
                "Maintained CI quality gates.",
                ("Python",),
                "impact",
                "domain",
            ),
            Bullet(
                "keep-2",
                "Improved framework reliability.",
                ("Python",),
                "impact",
                "domain",
            ),
            Bullet(
                "drop-long",
                f"Introduced {long_token} for stress-testing parser behavior.",
                ("Python",),
                "impact",
                "domain",
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(exp,),
        skills_by_category={},
    )
    resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "keep-1": {"confidence": 0.95},
            "keep-2": {"confidence": 0.9},
            "drop-long": {"confidence": 0.0},
        },
    )

    trimmed = trim_by_rules(resume)

    kept_ids = [bullet.id for bullet in trimmed.experiences[0].bullets]
    assert kept_ids == ["keep-1", "keep-2"]


def test_estimate_wrapped_line_count_counts_overlong_tokens() -> None:
    line_width = build_resume.DEFAULT_BULLET_LINE_WIDTH
    long_token = "x" * (line_width * 3 + 7)

    estimated = build_resume._estimate_wrapped_line_count(long_token, line_width)

    assert estimated == math.ceil(len(long_token) / line_width)


def test_trim_by_rules_logs_when_line_budget_cannot_meet_floor(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_MAX_BULLET_LINES", 1)
    profile = load_profile(PROFILE)
    exp_one = Experience(
        id="exp-floor-1",
        job_title="Role One",
        company="Company",
        start_date="2020-01",
        end_date="2021-01",
        general_role_description="Role one summary.",
        related_skills=(),
        bullets=(
            Bullet(
                "one-a", "Maintained CI quality gates.", ("Python",), "impact", "domain"
            ),
            Bullet(
                "one-b", "Improved test diagnostics.", ("Pytest",), "impact", "domain"
            ),
        ),
    )
    exp_two = Experience(
        id="exp-floor-2",
        job_title="Role Two",
        company="Company",
        start_date="2021-02",
        end_date="2022-02",
        general_role_description="Role two summary.",
        related_skills=(),
        bullets=(
            Bullet(
                "two-a",
                "Expanded regression coverage.",
                ("Testing",),
                "impact",
                "domain",
            ),
            Bullet(
                "two-b",
                "Automated validation checks.",
                ("Automation",),
                "impact",
                "domain",
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(exp_one, exp_two),
        skills_by_category={},
    )
    resume = type(resume)(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "one-a": {"confidence": 0.9},
            "one-b": {"confidence": 0.8},
            "two-a": {"confidence": 0.7},
            "two-b": {"confidence": 0.6},
        },
    )
    with caplog.at_level(logging.WARNING):
        trimmed = trim_by_rules(resume)
    assert all(
        len(experience.bullets) == build_resume.DEFAULT_MIN_BULLETS_PER_EXPERIENCE
        for experience in trimmed.experiences
    )
    remaining_lines = build_resume._estimate_total_bullet_lines(
        [list(experience.bullets) for experience in trimmed.experiences]
    )
    assert remaining_lines > build_resume.DEFAULT_MAX_BULLET_LINES
    assert any(
        "Line-budget target not reached" in message for message in caplog.messages
    )


def test_load_experiences_defaults_bullet_dates_to_role_dates(tmp_path: Path) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp1"
job_title = "Role"
company = "Example"
start_date = "2018-01"
end_date = "2020-01"
general_role_description = "Role summary"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Did thing"
skills = ["Python"]
impact_type = "impact"
domain = "domain"

[[experience.bullet_bank]]
id = "b2"
text = "Did other thing"
skills = ["Python"]
impact_type = "impact"
domain = "domain"
start_date = "2019-03"
end_date = "2019-12"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)

    assert experiences[0].bullets[0].start_date == "2018-01"
    assert experiences[0].bullets[0].end_date == "2020-01"
    assert experiences[0].bullets[1].start_date == "2019-03"
    assert experiences[0].bullets[1].end_date == "2019-12"


def test_load_experiences_strips_role_dates_before_bullet_fallback(
    tmp_path: Path,
) -> None:
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(
        """
[[experience]]
id = "exp1"
job_title = "Role"
company = "Example"
start_date = " 2018-01 "
end_date = " 2020-01 "
general_role_description = "Role summary"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Did thing"
skills = ["Python"]
impact_type = "impact"
domain = "domain"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    experiences = load_experiences(experience_path)

    assert experiences[0].start_date == "2018-01"
    assert experiences[0].end_date == "2020-01"
    assert experiences[0].bullets[0].start_date == "2018-01"
    assert experiences[0].bullets[0].end_date == "2020-01"


def test_render_outputs_show_role_dates_not_bullet_dates(tmp_path: Path) -> None:
    experience = Experience(
        id="exp-date-visibility",
        job_title="Role",
        company="Example",
        start_date="2018-01",
        end_date="2020-01",
        general_role_description="Role summary",
        related_skills=("Python",),
        bullets=(
            Bullet(
                id="b1",
                text="Did thing",
                skills=("Python",),
                impact_type="impact",
                domain="domain",
                start_date="2019-03",
                end_date="2019-12",
            ),
            Bullet(
                id="b2",
                text="Did another thing",
                skills=("Python",),
                impact_type="impact",
                domain="domain",
                start_date="2018-05",
                end_date="2018-07",
            ),
        ),
    )

    resume = assemble_baseline_resume(
        profile=CURRENT_PROFILE,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(experience,),
        skills_by_category={"Core": ["Python"]},
    )

    html_path = tmp_path / "resume.html"
    md_path = tmp_path / "resume.md"
    txt_path = tmp_path / "resume_snapshot.txt"

    build_resume.render_html(resume, html_path)
    build_resume.render_markdown(resume, md_path)
    build_resume.write_text_snapshot(resume, txt_path)

    html_text = html_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    txt_text = txt_path.read_text(encoding="utf-8")

    assert "January 2018 - January 2020" in html_text
    assert "2018-01 - 2020-01" in md_text
    assert "date_range: 2018-01 - 2020-01" in txt_text

    assert "2019-03" not in html_text
    assert "2019-12" not in html_text
    assert "2019-03" not in md_text
    assert "2019-12" not in md_text
    assert "2019-03" not in txt_text
    assert "2019-12" not in txt_text


def test_prepare_display_experiences_excludes_roles_older_than_15_years() -> None:
    experiences = (
        Experience(
            id="old",
            job_title="Old role",
            company="Example",
            start_date="2000-01",
            end_date="2009-01",
            general_role_description="Old summary",
            related_skills=("Python",),
            bullets=(
                Bullet("old-b1", "Old bullet", ("Python",), "impact", "domain"),
                Bullet("old-b2", "Old bullet 2", ("Python",), "impact", "domain"),
            ),
        ),
        Experience(
            id="recent",
            job_title="Recent role",
            company="Example",
            start_date="2018-01",
            end_date="2024-01",
            general_role_description="Recent summary",
            related_skills=("Python",),
            bullets=(
                Bullet("recent-b1", "Recent bullet", ("Python",), "impact", "domain"),
                Bullet("recent-b2", "Recent bullet 2", ("Python",), "impact", "domain"),
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=CURRENT_PROFILE,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )

    original_now = build_resume._current_year_month
    build_resume._current_year_month = lambda: (2026, 4)
    try:
        display = build_resume._prepare_display_experiences(resume)
    finally:
        build_resume._current_year_month = original_now

    assert [experience.id for experience in display] == ["recent"]


def test_prepare_display_experiences_keeps_undated_roles_and_sorts_by_relevance() -> (
    None
):
    experiences = (
        Experience(
            id="dated-low",
            job_title="Dated low relevance",
            company="Example",
            start_date="2020-01",
            end_date="2024-01",
            general_role_description="Summary",
            related_skills=("Python",),
            bullets=(
                Bullet("low-a", "Low confidence", ("Python",), "impact", "domain"),
                Bullet("low-b", "Low confidence 2", ("Python",), "impact", "domain"),
            ),
        ),
        Experience(
            id="undated",
            job_title="Undated role",
            company="Example",
            start_date="",
            end_date="",
            general_role_description="Summary",
            related_skills=("Python",),
            bullets=(
                Bullet("u-a", "Undated bullet", ("Python",), "impact", "domain"),
                Bullet("u-b", "Undated bullet 2", ("Python",), "impact", "domain"),
            ),
        ),
        Experience(
            id="dated-high",
            job_title="Dated high relevance",
            company="Example",
            start_date="2019-01",
            end_date="2024-01",
            general_role_description="Summary",
            related_skills=("Python",),
            bullets=(
                Bullet("high-a", "High confidence", ("Python",), "impact", "domain"),
                Bullet("high-b", "High confidence 2", ("Python",), "impact", "domain"),
            ),
        ),
    )

    resume = assemble_baseline_resume(
        profile=CURRENT_PROFILE,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={},
    )
    resume = build_resume.ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "low-a": {"confidence": 0.1},
            "low-b": {"confidence": 0.1},
            "u-a": {"confidence": 0.2},
            "u-b": {"confidence": 0.2},
            "high-a": {"confidence": 0.9},
            "high-b": {"confidence": 0.9},
        },
    )

    original_now = build_resume._current_year_month
    build_resume._current_year_month = lambda: (2026, 4)
    try:
        display = build_resume._prepare_display_experiences(resume)
    finally:
        build_resume._current_year_month = original_now

    assert [experience.id for experience in display] == [
        "dated-high",
        "undated",
        "dated-low",
    ]


def test_apply_display_experience_selection_filters_enrichment_for_removed_roles() -> (
    None
):
    experiences = (
        Experience(
            id="old",
            job_title="Old role",
            company="Example",
            start_date="2000-01",
            end_date="2009-01",
            general_role_description="Old summary",
            related_skills=("LegacySkill",),
            bullets=(
                Bullet("old-b1", "Old bullet", ("LegacySkill",), "impact", "domain"),
                Bullet("old-b2", "Old bullet 2", ("LegacySkill",), "impact", "domain"),
            ),
        ),
        Experience(
            id="recent",
            job_title="Recent role",
            company="Example",
            start_date="2019-01",
            end_date="2024-01",
            general_role_description="Recent summary",
            related_skills=("CurrentSkill",),
            bullets=(
                Bullet(
                    "recent-b1", "Recent bullet", ("CurrentSkill",), "impact", "domain"
                ),
                Bullet(
                    "recent-b2",
                    "Recent bullet 2",
                    ("CurrentSkill",),
                    "impact",
                    "domain",
                ),
            ),
        ),
    )
    resume = assemble_baseline_resume(
        profile=CURRENT_PROFILE,
        target_role="",
        target_company="",
        job_context=None,
        experiences=experiences,
        skills_by_category={"Legacy": ["LegacySkill"], "Current": ["CurrentSkill"]},
    )
    resume = build_resume.ResumeIR(
        profile=resume.profile,
        target_role=resume.target_role,
        target_company=resume.target_company,
        display_headline=resume.display_headline,
        job_context=resume.job_context,
        experiences=resume.experiences,
        skills_by_category=resume.skills_by_category,
        enrichment_by_bullet_id={
            "old-b1": {"confidence": 0.1},
            "old-b2": {"confidence": 0.1},
            "recent-b1": {"confidence": 0.9},
            "recent-b2": {"confidence": 0.8},
        },
    )

    original_now = build_resume._current_year_month
    build_resume._current_year_month = lambda: (2026, 4)
    try:
        filtered = build_resume._apply_display_experience_selection(resume)
    finally:
        build_resume._current_year_month = original_now

    assert [experience.id for experience in filtered.experiences] == ["recent"]
    assert filtered.enrichment_by_bullet_id == {
        "recent-b1": {"confidence": 0.9},
        "recent-b2": {"confidence": 0.8},
    }


# ---------------------------------------------------------------------------
# --cover-letter flag stub (issue #227; real generator: #229)
# ---------------------------------------------------------------------------


# Note: the prior `test_build_resume_cli_cover_letter_flag_emits_stub`
# tested PR #231's stub generator (a placeholder markdown file). After
# PR #223 replaced the stub with the v1 LLM-driven generator (see issue
# #229), an end-to-end CLI test of `--cover-letter` requires fixture-
# mode setup (RESUME_BUILDER_LLM_FIXTURE=1 + an experience_db whose
# inputs hash into the fixture cache). The unit-level coverage of the
# new wiring lives in tests/scripts/test_build_cover_letter.py
# (test_cover_letter_module_invokes_run_pipeline_collecting_paths);
# the missing CLI-level end-to-end is tracked outside this PR.


def test_build_resume_cli_no_cover_letter_flag_skips_cover_letter_dir(
    tmp_path: Path,
) -> None:
    """Without --cover-letter, no cover_letters/ subdir is created."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
    )
    assert result.returncode == 0, result.stderr
    assert not (output_dir / "cover_letters").exists()


def test_run_pipeline_tolerates_namespace_without_cover_letter_attr(
    tmp_path: Path,
) -> None:
    """run_pipeline must default to no cover letter when the field is absent."""
    import argparse

    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    output_dir = tmp_path / "out"

    pipeline_args = argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="",
        job_text_file=None,
        target_role="Staff Software Engineer",
        output_dir=output_dir,
        processing_mode="raw",
        outputs=("html", "md"),
        template="modern",
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == 0
    assert not (output_dir / "cover_letters").exists()


# ---------------------------------------------------------------------------
# --outputs flag (issue #206)
# ---------------------------------------------------------------------------


def _outputs_cli(
    *,
    output_dir: Path,
    profile_path: Path,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    args = [
        sys.executable,
        str(SCRIPT),
        "--profile",
        str(profile_path),
        "--experience-db",
        str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
        "--output-dir",
        str(output_dir),
        "--target-role",
        "Staff Software Engineer",
        "--processing-mode",
        "processed",
        "--allow-overflow-pdf",
        *extra_args,
    ]
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_outputs_default_writes_pdf_docx_and_ir(tmp_path: Path) -> None:
    """Default --outputs=pdf,docx produces PDF + DOCX + IR snapshots; no HTML/MD."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(output_dir=output_dir, profile_path=profile_path)
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "company_resume.pdf").exists()
    assert (output_dir / "resumes" / "company_resume.docx").exists()
    assert (
        output_dir / "resumes" / "latest_resume_processed_ir_snapshot.json"
    ).exists()
    assert (output_dir / "resumes" / "latest_resume_processed_ir_snapshot.txt").exists()

    # HTML and MD absent under default --outputs=pdf,docx.
    assert not (output_dir / "resumes" / "latest_resume_processed.html").exists()
    assert not (
        output_dir / "resumes" / "latest_default_resume_processed.html"
    ).exists()
    assert not (output_dir / "resumes" / "latest_resume_processed.md").exists()


def test_outputs_all_four_formats(tmp_path: Path) -> None:
    """`--outputs=pdf,docx,md,html` writes all four canonical artifacts."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "pdf,docx,md,html"),
    )
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "company_resume.pdf").exists()
    assert (output_dir / "resumes" / "company_resume.docx").exists()
    assert (output_dir / "resumes" / "latest_resume_processed.md").exists()
    assert (output_dir / "resumes" / "latest_resume_processed.html").exists()
    assert (output_dir / "resumes" / "latest_default_resume_processed.html").exists()


def test_outputs_html_and_md_only_skips_pdf_and_docx(tmp_path: Path) -> None:
    """`--outputs=html,md` writes neither PDF nor DOCX."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "html,md"),
    )
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "latest_resume_processed.html").exists()
    assert (output_dir / "resumes" / "latest_resume_processed.md").exists()
    assert not (output_dir / "resumes" / "company_resume.pdf").exists()
    assert not (output_dir / "resumes" / "company_resume.docx").exists()


def test_outputs_unknown_token_rejected(tmp_path: Path) -> None:
    """Unknown --outputs token is rejected with a clear error listing valid tokens."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "pdf,xml"),
    )
    assert result.returncode != 0
    assert "unknown token(s) xml" in result.stderr
    assert "valid tokens: pdf, docx, md, html" in result.stderr


def test_outputs_filename_overrides_land_under_output_dir(tmp_path: Path) -> None:
    """`--pdf-filename`/`--docx-filename` overrides land under --output-dir."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=(
            "--outputs",
            "pdf,docx",
            "--pdf-filename",
            "custom.pdf",
            "--docx-filename",
            "nested/custom.docx",
        ),
    )
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "custom.pdf").exists()
    assert (output_dir / "resumes" / "nested" / "custom.docx").exists()
    # Canonical names not produced when overrides are supplied.
    assert not (output_dir / "resumes" / "company_resume.pdf").exists()
    assert not (output_dir / "resumes" / "company_resume.docx").exists()


def test_outputs_filename_override_rejects_absolute_path(tmp_path: Path) -> None:
    """Absolute path in --pdf-filename is rejected."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "pdf", "--pdf-filename", "/tmp/evil.pdf"),
    )
    assert result.returncode != 0
    assert "--pdf-filename must be a path under" in result.stderr
    assert "absolute paths are not allowed" in result.stderr


def test_outputs_filename_override_rejects_path_traversal(tmp_path: Path) -> None:
    """Path traversal (../) in --docx-filename is rejected."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "docx", "--docx-filename", "../escape.docx"),
    )
    assert result.returncode != 0
    assert "--docx-filename must remain under" in result.stderr
    assert "path traversal is not allowed" in result.stderr


def test_outputs_pdf_with_include_private_projects_renders_section(
    tmp_path: Path,
) -> None:
    """--include-private-projects × --outputs=pdf includes Independent Projects in PDF."""
    pypdf = pytest.importorskip("pypdf")
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "pdf", "--include-private-projects"),
    )
    assert result.returncode == 0, result.stderr

    pdf_path = output_dir / "resumes" / "company_resume.pdf"
    assert pdf_path.exists()
    reader = pypdf.PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Independent Projects" in text


def test_outputs_company_slug_drives_canonical_filename(tmp_path: Path) -> None:
    """--company slug feeds <slug>_resume.{pdf,docx} canonical naming."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(
        output_dir=output_dir,
        profile_path=profile_path,
        extra_args=("--outputs", "pdf,docx", "--company", "Acme Corp"),
    )
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "acme_corp_resume.pdf").exists()
    assert (output_dir / "resumes" / "acme_corp_resume.docx").exists()
    assert not (output_dir / "resumes" / "company_resume.pdf").exists()


def test_export_resume_documents_shim_produces_canonical_outputs(
    tmp_path: Path,
) -> None:
    """The export_resume_documents.py shim still produces canonical DOCX+PDF."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "export_resume_documents.py"),
            "--profile",
            str(profile_path),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--output-dir",
            str(output_dir),
            "--target-role",
            "Staff Software Engineer",
            "--processing-mode",
            "processed",
            "--allow-overflow-pdf",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (output_dir / "resumes" / "company_resume.pdf").exists()
    assert (output_dir / "resumes" / "company_resume.docx").exists()


# ---------------------------------------------------------------------------
# --company auto-derive from JD (issue #212)
# ---------------------------------------------------------------------------


def test_company_auto_derived_from_job_text_file(tmp_path: Path) -> None:
    """No --company + --job-text-file with a Company: header → snake_case slug."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(
        "Company: Elite Technology\n\nSenior Staff Software Engineer.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            str(profile_path),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--allow-overflow-pdf",
            "--outputs",
            "pdf",
            "--job-text-file",
            str(jd_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "auto-derived from job description" in result.stdout
    assert (output_dir / "resumes" / "elite_technology_resume.pdf").exists()
    assert not (output_dir / "resumes" / "company_resume.pdf").exists()


def test_company_explicit_overrides_jd_derived(tmp_path: Path) -> None:
    """Explicit --company wins over a JD-derived company name."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text("Company: Elite Technology\n\nRole.\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            str(profile_path),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--allow-overflow-pdf",
            "--outputs",
            "pdf",
            "--job-text-file",
            str(jd_path),
            "--company",
            "Acme Corp",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "auto-derived from job description" not in result.stdout
    assert (output_dir / "resumes" / "acme_corp_resume.pdf").exists()
    assert not (output_dir / "resumes" / "elite_technology_resume.pdf").exists()


def test_build_resume_cli_fails_when_jd_supplied_but_company_not_derivable(
    tmp_path: Path,
) -> None:
    """JD supplied but neither deterministic nor LLM tier finds a company,
    and no explicit --company → exit non-zero with an actionable message and
    no artifacts written. Prevents silent routing under data/outputs/baseline/
    when extraction simply missed."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    jd_path = tmp_path / "jd.txt"
    # Free-form JD without a `Company:` header or other deterministic signal.
    # LLM tier is gated off by default in tests (RESUME_BUILDER_LLM_ENABLED unset).
    jd_path.write_text(
        "Senior Staff Software Engineer focused on payments and risk.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            str(profile_path),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--allow-overflow-pdf",
            "--outputs",
            "pdf",
            "--job-text-file",
            str(jd_path),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, result.stdout
    assert "Could not derive a company name" in result.stderr
    assert "--company" in result.stderr
    # No artifacts written on the failed run.
    resumes_dir = output_dir / "resumes"
    if resumes_dir.exists():
        assert not any(resumes_dir.glob("*_resume.pdf")), list(resumes_dir.iterdir())
        assert not any(resumes_dir.glob("*_resume.docx")), list(resumes_dir.iterdir())


def test_company_falls_back_to_default_when_no_jd(tmp_path: Path) -> None:
    """No --company and no JD → fallback to 'company' slug."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            str(profile_path),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--allow-overflow-pdf",
            "--outputs",
            "pdf",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "auto-derived from job description" not in result.stdout
    assert (output_dir / "resumes" / "company_resume.pdf").exists()


def test_extract_company_via_llm_returns_llm_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit-level: _extract_company_via_llm returns whatever the LLM payload
    says for the `company` field, with a stubbed LLMClient."""
    from resume_builder.build_resume import _extract_company_via_llm
    from resume_builder.jd_ingest import JobContext

    class _FakeClient:
        @classmethod
        def from_env(cls) -> _FakeClient:
            return cls()

        def complete_json(
            self,
            *,
            namespace: str,
            system_prompt: str,
            user_payload: dict[str, object],
        ) -> dict[str, Any]:
            assert namespace == "extract_company_name"
            return {"company": "Elite Technology"}

    monkeypatch.setattr(build_resume, "LLMClient", _FakeClient)

    jc = JobContext(
        input_url="",
        normalized_url="",
        source="job-text-file",
        role_hint="Engineer",
        company_name="",
        job_id="",
        fetch_status="provided_text",
        page_title="Senior Engineer at Elite Technology",
        description_excerpt="Build payment systems.",
        notes=(),
        company_research=None,
    )
    assert _extract_company_via_llm(jc) == "Elite Technology"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Western Union, you are an Individual Contributor (IC) responsible "
            "for the architectural integrity and technical evolution of "
            "mission-critical systems",
            "Western Union",
        ),
        ("At Acme Corp", "Acme Corp"),
        ("Elite Technology", "Elite Technology"),
        ("Join us at Globex", "Globex"),
        ("Stripe is a payments infrastructure company", "Stripe"),
        ("Acme Corp — building the future of payments", "Acme Corp"),
        ("Acme Corp— hiring now", "Acme Corp"),
        ("  Stripe.  ", "Stripe"),
        ("U.S. Bank", "U.S. Bank"),
        ("Acme Inc.", "Acme Inc"),
        ("Acme. building payments", "Acme"),
        ("", ""),
        ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", ""),
        ("one two three four five six", ""),
    ],
)
def test_clean_llm_company_name_truncates_trailing_prose(
    raw: str, expected: str
) -> None:
    """#322: post-processor strips sentence prose, leading prepositions, and
    rejects implausibly long responses."""
    from resume_builder.build_resume import _clean_llm_company_name

    assert _clean_llm_company_name(raw) == expected


def test_extract_company_via_llm_strips_jd_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#322: when the LLM echoes the JD opening sentence, the extractor
    returns only the leading company name."""
    from resume_builder.build_resume import _extract_company_via_llm
    from resume_builder.jd_ingest import JobContext

    class _FakeClient:
        @classmethod
        def from_env(cls) -> _FakeClient:
            return cls()

        def complete_json(
            self,
            *,
            namespace: str,
            system_prompt: str,
            user_payload: dict[str, object],
        ) -> dict[str, Any]:
            return {
                "company": (
                    "Western Union, you are an Individual Contributor (IC) "
                    "responsible for the architectural integrity and "
                    "technical evolution of mission-critical systems"
                )
            }

    monkeypatch.setattr(build_resume, "LLMClient", _FakeClient)

    jc = JobContext(
        input_url="",
        normalized_url="",
        source="company-site",
        role_hint="Staff Software Engineer",
        company_name="",
        job_id="",
        fetch_status="rendered",
        page_title="Staff Software Engineer",
        description_excerpt=(
            "At Western Union, you are an Individual Contributor (IC) "
            "responsible for the architectural integrity..."
        ),
        notes=(),
        company_research=None,
    )
    assert _extract_company_via_llm(jc) == "Western Union"


def test_run_pipeline_uses_llm_company_in_output_filename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration: when the deterministic ingest returns no company name and
    LLM is enabled, run_pipeline routes the JD through _extract_company_via_llm
    and the resulting slug shapes the canonical filename."""
    import argparse as _argparse

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    jd_path = tmp_path / "jd.txt"
    # Free-form text the deterministic regex extractor cannot match
    # (no `Company:` header, no `join X` pattern).
    jd_path.write_text(
        "Senior Staff Software Engineer at Elite Technology, "
        "focused on payments and risk.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(build_resume, "_llm_stage_enabled", lambda: True)
    monkeypatch.setattr(
        build_resume,
        "_extract_company_via_llm",
        lambda _job_context: "Elite Technology",
    )

    pipeline_args = _argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="",
        job_text_file=jd_path,
        target_role="Staff Software Engineer",
        output_dir=output_dir,
        processing_mode="processed",
        outputs=("pdf",),
        company=None,
        pdf_filename=None,
        docx_filename=None,
        allow_overflow_pdf=True,
        post_layout_cleanup="enabled",
        template="modern",
        include_private_projects=False,
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == 0
    # LLM-derived company drove the canonical slug.
    assert (output_dir / "resumes" / "elite_technology_resume.pdf").exists()
    assert not (output_dir / "resumes" / "company_resume.pdf").exists()
    # The pipeline mutates args.company in place to the resolved name.
    assert pipeline_args.company == "Elite Technology"


# ---------------------------------------------------------------------------
# ATS host company extraction (issue #212 / greenhouse follow-up)
# ---------------------------------------------------------------------------


def test_ats_extraction_picks_company_from_greenhouse_path() -> None:
    """`job-boards.greenhouse.io/<company>/jobs/<id>` → company is the path slug,
    NOT the netloc's first label (which is "job-boards")."""
    from urllib.parse import urlparse

    from resume_builder.jd_ingest import _extract_company_name, _infer_source

    parsed = urlparse(
        "https://job-boards.greenhouse.io/elitetechnology/jobs/5206489008"
    )
    source = _infer_source(parsed.netloc)
    assert source == "ats"
    assert (
        _extract_company_name(
            source=source,
            netloc=parsed.netloc,
            path=parsed.path,
            page_title="",
            description="",
        )
        == "elitetechnology"
    )


def test_ats_extraction_handles_lever_workday_ashby_bamboohr() -> None:
    """Common ATS host shapes resolve to the correct company slug."""
    from urllib.parse import urlparse

    from resume_builder.jd_ingest import _extract_company_name, _infer_source

    cases = [
        ("https://jobs.lever.co/acme/abc-123", "acme"),
        ("https://nvidia.wd5.myworkdayjobs.com/job/r12345", "nvidia"),
        ("https://jobs.ashbyhq.com/anthropic/abc", "anthropic"),
        ("https://acme.bamboohr.com/jobs/view.php?id=12", "acme"),
    ]
    for url, expected in cases:
        parsed = urlparse(url)
        source = _infer_source(parsed.netloc)
        assert source == "ats", f"expected ats source for {url}, got {source}"
        assert (
            _extract_company_name(
                source=source,
                netloc=parsed.netloc,
                path=parsed.path,
                page_title="",
                description="",
            )
            == expected
        ), f"wrong company for {url}"


def test_company_site_extraction_unchanged_for_direct_career_pages() -> None:
    """Direct company career pages still use netloc's first label."""
    from urllib.parse import urlparse

    from resume_builder.jd_ingest import _extract_company_name, _infer_source

    parsed = urlparse("https://anthropic.com/careers/job-12")
    source = _infer_source(parsed.netloc)
    assert source == "company-site"
    assert (
        _extract_company_name(
            source=source,
            netloc=parsed.netloc,
            path=parsed.path,
            page_title="",
            description="",
        )
        == "Anthropic"
    )


# ---------------------------------------------------------------------------
# Two-page PDF page-fit regression (issue #219)
# ---------------------------------------------------------------------------


def test_processed_build_renders_two_page_pdf_at_full_content_shape(
    tmp_path: Path,
) -> None:
    """Pin the points-based budget calibration: a build with the full content
    shape (cross-org leadership, selected achievements, all displayed
    experiences, education, leadership) must produce a 2-page PDF without
    --allow-overflow-pdf. Locks in the issue #219 fix.
    """
    pypdf = pytest.importorskip("pypdf")

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(
        "Company: Elite Technology\n\n"
        "Senior Staff Software Engineer for automation and platform "
        "engineering work across multiple product teams.\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profile",
            str(PROFILE),
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--skills-matrix",
            str(REPO_ROOT / "data" / "skills" / "skills_matrix.csv"),
            "--output-dir",
            str(output_dir),
            "--processing-mode",
            "processed",
            "--outputs",
            "pdf",
            "--job-text-file",
            str(jd_path),
            "--company",
            "Elite Technology",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"build failed without --allow-overflow-pdf: stderr={result.stderr!r} "
        f"stdout={result.stdout!r}"
    )

    pdf_path = output_dir / "resumes" / "elite_technology_resume.pdf"
    assert pdf_path.exists(), f"expected pdf at {pdf_path}"
    reader = pypdf.PdfReader(str(pdf_path))
    assert len(reader.pages) == 2, (
        f"expected 2-page PDF, got {len(reader.pages)} — page-fit estimator "
        "and renderer have drifted; rerun build and inspect "
        "_compute_bullet_line_budget vs. render_pdf in document_export.py"
    )


# ----- issue #247: warn when JD ingest looks essentially empty ----------


def _make_job_context(description_excerpt: str) -> jd_ingest.JobContext:
    """Build a minimal JobContext for warning-helper tests."""
    return jd_ingest.JobContext(
        input_url="https://example.com/job",
        normalized_url="https://example.com/job",
        source="company-site",
        role_hint="",
        company_name="",
        job_id="",
        fetch_status="ok",
        page_title="",
        description_excerpt=description_excerpt,
        notes=(),
        company_research=None,
    )


def test_warn_if_jd_ingest_empty_fires_on_empty_description(
    capsys: pytest.CaptureFixture[str],
) -> None:
    job_url = "https://careers.example.com/listing/123"
    build_resume._warn_if_jd_ingest_empty(
        job_context=_make_job_context(""), job_url=job_url
    )
    err = capsys.readouterr().err
    assert "WARNING:" in err
    assert "JD ingest produced little or no usable content" in err
    assert job_url in err
    assert "--job-text-file" in err
    assert "issues/247" in err


def test_warn_if_jd_ingest_empty_fires_on_short_description(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A 100-char fetch is well under the 200-char threshold."""
    short = "A" * 100
    build_resume._warn_if_jd_ingest_empty(
        job_context=_make_job_context(short),
        job_url="https://example.com/job",
    )
    err = capsys.readouterr().err
    assert "WARNING:" in err
    assert "100 chars" in err


def test_warn_if_jd_ingest_empty_silent_when_excerpt_is_substantive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    substantive = "We are hiring a Staff Engineer. " * 40  # ~1280 chars
    build_resume._warn_if_jd_ingest_empty(
        job_context=_make_job_context(substantive),
        job_url="https://example.com/job",
    )
    err = capsys.readouterr().err
    assert err == ""


def test_warn_if_jd_ingest_empty_text_with_llm_enabled(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With LLM stages on, the effect line names the LLM-tailoring impact."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    build_resume._warn_if_jd_ingest_empty(
        job_context=_make_job_context(""),
        job_url="https://example.com/job",
    )
    err = capsys.readouterr().err
    assert "LLM tailoring stages will run on near-empty context" in err


def test_warn_if_jd_ingest_empty_text_with_llm_disabled(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With LLM off, the effect line says so explicitly so users aren't misled.

    Round-2 review on PR #249: previous wording presumed LLM stages would
    run, but they're gated by _llm_stage_enabled().
    """
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    build_resume._warn_if_jd_ingest_empty(
        job_context=_make_job_context(""),
        job_url="https://example.com/job",
    )
    err = capsys.readouterr().err
    assert "LLM tailoring is disabled" in err
    assert "RESUME_BUILDER_LLM_ENABLED=1" in err
    assert "LLM tailoring stages will run on near-empty context" not in err


# ---------------------------------------------------------------------------
# --top-skills-cap CLI validation (issue #256, PR #273 review)
# ---------------------------------------------------------------------------


def test_parse_top_skills_cap_accepts_in_range_values() -> None:
    assert build_resume._parse_top_skills_cap("1") == 1
    assert build_resume._parse_top_skills_cap("46") == 46
    assert build_resume._parse_top_skills_cap("59") == 59


def test_parse_top_skills_cap_rejects_zero_and_negative() -> None:
    import argparse as _argparse

    with pytest.raises(_argparse.ArgumentTypeError, match=">= 1"):
        build_resume._parse_top_skills_cap("0")
    with pytest.raises(_argparse.ArgumentTypeError, match=">= 1"):
        build_resume._parse_top_skills_cap("-5")


def test_parse_top_skills_cap_rejects_oversized_values() -> None:
    import argparse as _argparse

    with pytest.raises(_argparse.ArgumentTypeError, match="< 60"):
        build_resume._parse_top_skills_cap("60")
    with pytest.raises(_argparse.ArgumentTypeError, match="< 60"):
        build_resume._parse_top_skills_cap("9999")


def test_parse_top_skills_cap_rejects_non_integer() -> None:
    import argparse as _argparse

    with pytest.raises(_argparse.ArgumentTypeError, match="must be an integer"):
        build_resume._parse_top_skills_cap("forty-six")


# ----- issue #247 fix-4: --require-jd-context hard gate -----------------


def _minimal_resume_ir(
    *,
    summary: str = "Software engineer.",
    job_context: jd_ingest.JobContext | None = None,
    target_role: str = "Staff Software Engineer",
    target_company: str = "Acme",
) -> build_resume.ResumeIR:
    """Build the smallest ResumeIR that exercises summarize_profile_for_role.

    Empty experiences + skills_by_category is sufficient because
    _generate_jd_tailored_summary_via_llm only reads them as prompt
    context — the LLM is mocked, and the deterministic fallback path
    has its own existing test coverage.
    """
    profile = build_resume.Profile(
        name="Jonathan Smith",
        headline="",
        location="",
        email="",
        phone="",
        website="",
        linkedin="",
        github="",
        summary=summary,
        education_entries=(),
        leadership_community_entries=(),
    )
    return build_resume.ResumeIR(
        profile=profile,
        target_role=target_role,
        target_company=target_company,
        display_headline="",
        job_context=job_context,
        experiences=(),
        skills_by_category={},
    )


@pytest.mark.parametrize(
    "excerpt, expected",
    [
        ("", True),
        ("A" * 50, True),  # well below 200-char threshold
        ("A" * 199, True),
        ("A" * 200, False),  # exactly at the threshold
        ("A" * 1000, False),
    ],
)
def test_jd_context_below_threshold(excerpt: str, expected: bool) -> None:
    """Threshold check used by both the WARNING and the hard gate."""
    assert (
        build_resume._jd_context_below_threshold(_make_job_context(excerpt)) is expected
    )


@pytest.mark.parametrize(
    "flag, env, expected",
    [
        (False, None, False),
        (True, None, True),
        (False, "1", True),
        (True, "1", True),
        # Non-"1" env values are treated as off (only the literal "1" enables).
        (False, "0", False),
        (False, "true", False),
        (False, "", False),
        # Conflict: explicit flag wins. Setting the env var to "0" while
        # also passing --require-jd-context does NOT disable gating.
        # Documented behavior — env can enable, but it cannot override-down
        # an explicit per-call flag.
        (True, "0", True),
        (True, "", True),
        (True, "false", True),
    ],
)
def test_jd_context_required_resolves_flag_and_env(
    monkeypatch: pytest.MonkeyPatch,
    flag: bool,
    env: str | None,
    expected: bool,
) -> None:
    if env is None:
        monkeypatch.delenv(build_resume.REQUIRE_JD_CONTEXT_ENV, raising=False)
    else:
        monkeypatch.setenv(build_resume.REQUIRE_JD_CONTEXT_ENV, env)
    ns = argparse.Namespace(require_jd_context=flag)
    assert build_resume._jd_context_required(ns) is expected


def test_jd_context_required_handles_namespace_without_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """getattr default keeps run_pipeline tolerant of legacy callers."""
    monkeypatch.delenv(build_resume.REQUIRE_JD_CONTEXT_ENV, raising=False)
    assert build_resume._jd_context_required(argparse.Namespace()) is False


def test_run_pipeline_returns_jd_context_required_when_gate_fires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end gate path: empty ingest + flag set => non-zero exit."""
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    def fake_ingest(_url: str) -> jd_ingest.JobContext:
        return _make_job_context("")  # 0-char excerpt

    monkeypatch.setattr(build_resume, "ingest_job_context", fake_ingest)
    monkeypatch.delenv(build_resume.REQUIRE_JD_CONTEXT_ENV, raising=False)

    pipeline_args = argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="https://careers.example.com/listing/123",
        job_text_file=None,
        target_role="",
        output_dir=tmp_path / "out",
        processing_mode="processed",
        outputs=("pdf",),
        company=None,
        pdf_filename=None,
        docx_filename=None,
        allow_overflow_pdf=True,
        post_layout_cleanup="enabled",
        template="modern",
        include_private_projects=False,
        cover_letter=False,
        require_jd_context=True,  # gate ON
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == build_resume.EXIT_JD_CONTEXT_REQUIRED
    err = capsys.readouterr().err
    assert "ERROR: --require-jd-context" in err
    assert "0 chars" in err
    assert str(build_resume.EXIT_JD_CONTEXT_REQUIRED) in err
    # Source label names the offending input so the operator can find it.
    assert "--job-url https://careers.example.com/listing/123" in err


def test_run_pipeline_returns_jd_context_required_for_short_job_text_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Gate fires on the --job-text-file path too, not just --job-url.

    Round-2 review on PR #261 — the help text said 'when JD ingest
    produces less than N characters of description', but the gate was
    only wired to the --job-url branch. A too-short text file should
    fail-fast for the same reason: scripted runs that depend on JD
    context shouldn't silently ship an un-tailored baseline.
    """
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")
    short_jd = tmp_path / "jd.txt"
    short_jd.write_text("hello", encoding="utf-8")  # 5 chars; well under threshold
    monkeypatch.delenv(build_resume.REQUIRE_JD_CONTEXT_ENV, raising=False)

    pipeline_args = argparse.Namespace(
        profile=profile_path,
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        skills_matrix=REPO_ROOT / "data" / "skills" / "skills_matrix.csv",
        job_url="",
        job_text_file=short_jd,
        target_role="",
        output_dir=tmp_path / "out",
        processing_mode="processed",
        outputs=("pdf",),
        company=None,
        pdf_filename=None,
        docx_filename=None,
        allow_overflow_pdf=True,
        post_layout_cleanup="enabled",
        template="modern",
        include_private_projects=False,
        cover_letter=False,
        require_jd_context=True,
    )
    rc = build_resume.run_pipeline(pipeline_args)
    assert rc == build_resume.EXIT_JD_CONTEXT_REQUIRED
    err = capsys.readouterr().err
    assert "ERROR: --require-jd-context" in err
    assert "5 chars" in err
    assert "--job-text-file" in err
    assert str(short_jd) in err


# ----- issue #256: LLM-tailored summary in summarize_profile_for_role ----


@pytest.mark.parametrize(
    "excerpt, expected",
    [
        ("", False),
        ("A" * 100, False),
        ("A" * 199, False),
        ("A" * 200, True),
        ("A" * 1000, True),
    ],
)
def test_has_substantive_jd_context_threshold(excerpt: str, expected: bool) -> None:
    """_has_substantive_jd_context shares its threshold with the warn path."""
    resume = _minimal_resume_ir(job_context=_make_job_context(excerpt))
    assert build_resume._has_substantive_jd_context(resume) is expected


def test_has_substantive_jd_context_returns_false_when_no_context() -> None:
    resume = _minimal_resume_ir(job_context=None)
    assert build_resume._has_substantive_jd_context(resume) is False


class _LLMSummaryFakeClient:
    """Pluggable stand-in for LLMClient.from_env() in summary tests."""

    response_payload: dict[str, Any] = {}
    raise_on_call: BaseException | None = None
    captured_namespace: str = ""
    captured_payload: dict[str, object] = {}

    @classmethod
    def from_env(cls) -> _LLMSummaryFakeClient:
        return cls()

    def complete_json(
        self,
        *,
        namespace: str,
        system_prompt: str,
        user_payload: dict[str, object],
    ) -> dict[str, Any]:
        type(self).captured_namespace = namespace
        type(self).captured_payload = dict(user_payload)
        exc = type(self).raise_on_call
        if exc is not None:
            raise exc
        return type(self).response_payload


def _install_fake_llm(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, Any] | None = None,
    raise_on_call: BaseException | None = None,
) -> type[_LLMSummaryFakeClient]:
    """Wire _LLMSummaryFakeClient as build_resume.LLMClient + reset state."""
    _LLMSummaryFakeClient.response_payload = payload or {}
    _LLMSummaryFakeClient.raise_on_call = raise_on_call
    _LLMSummaryFakeClient.captured_namespace = ""
    _LLMSummaryFakeClient.captured_payload = {}
    monkeypatch.setattr(build_resume, "LLMClient", _LLMSummaryFakeClient)
    return _LLMSummaryFakeClient


def _build_in_bounds_summary(words: int) -> str:
    return " ".join(["word"] * words)


def _build_layout_overflow_summary(words: int = 100) -> str:
    """Word-count-in-bounds but line-count-OUT-of-bounds for layout test.

    Each token is intentionally long so wrap_lines exceeds
    PROFILE_SUMMARY_MAX_LINES (6) when wrapped at
    PROFILE_SUMMARY_LINE_WIDTH (115, the same width
    _fit_profile_summary_layout uses) even though the word count
    itself sits inside the [PROFILE_SUMMARY_MIN_RATIO * MAX_WORDS,
    MAX_WORDS] budget (currently [90, 112]).
    """
    return " ".join(["extremelylongtoken"] * words)


def test_generate_jd_tailored_summary_returns_in_bounds_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In-bounds LLM output is accepted and gets a terminal period."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    summary = _build_in_bounds_summary(100)  # within [90, 112]; ~5 wrap lines @ 115
    fake = _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    out = build_resume._generate_jd_tailored_summary_via_llm(resume)

    assert out.startswith("word word")
    assert out.endswith(".")
    assert fake.captured_namespace == "jd_tailored_summary"
    # Prompt payload includes the JD excerpt, target role/company, and bounds.
    jd_excerpt = fake.captured_payload["jd_excerpt"]
    assert isinstance(jd_excerpt, str)
    assert "Real JD body" in jd_excerpt
    assert fake.captured_payload["target_role"] == "Staff Software Engineer"
    assert fake.captured_payload["target_company"] == "Acme"
    # Upper bound is the deterministic generator's PROFILE_SUMMARY_MAX_WORDS;
    # lower bound is the LLM-specific sanity floor _LLM_SUMMARY_MIN_WORDS so
    # real-world LLM output (~50-90 words) doesn't get rejected.
    assert fake.captured_payload["max_words"] == build_resume.PROFILE_SUMMARY_MAX_WORDS
    assert fake.captured_payload["min_words"] == build_resume._LLM_SUMMARY_MIN_WORDS


def test_generate_jd_tailored_summary_keeps_existing_terminal_punctuation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    summary = _build_in_bounds_summary(100) + "?"
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    out = build_resume._generate_jd_tailored_summary_via_llm(resume)
    assert out.endswith("?")
    assert not out.endswith("?.")


def test_generate_jd_tailored_summary_collapses_internal_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    words = _build_in_bounds_summary(100).split()
    summary = " ".join(words[:50]) + "\n\n\t" + " ".join(words[50:])
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    out = build_resume._generate_jd_tailored_summary_via_llm(resume)
    assert "\n" not in out
    assert "\t" not in out
    assert len(out.split()) == 100


def test_generate_jd_tailored_summary_strips_trailing_separators_before_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing ',' / ';' / ':' must not produce ',.' / ';.' / ':.' output.

    Issue #256 round-1 review — the deterministic generator explicitly
    rstrips ' ,;:' before adding the period; the LLM path now does the
    same.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    for trailing in (",", ";", ":", " ,", "  ;  ", "."):
        summary = _build_in_bounds_summary(100) + trailing
        _install_fake_llm(monkeypatch, payload={"summary": summary})
        resume = _minimal_resume_ir(
            job_context=_make_job_context("Real JD body. " * 30)
        )
        out = build_resume._generate_jd_tailored_summary_via_llm(resume)
        # Must end with a single sentence terminator and no doubled punctuation.
        assert out.endswith((".", "?", "!"))
        assert not out.endswith((",.", ";.", ":."))


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing summary key
        {"summary": ""},  # empty string
        {"summary": "   "},  # whitespace only
        {"summary": None},  # non-string
        {"summary": 123},  # non-string
    ],
)
def test_generate_jd_tailored_summary_rejects_malformed_responses(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    _install_fake_llm(monkeypatch, payload=payload)
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))
    assert build_resume._generate_jd_tailored_summary_via_llm(resume) == ""


@pytest.mark.parametrize("word_count", [0, 10, 29, 113, 200])
def test_generate_jd_tailored_summary_rejects_out_of_bounds_word_count(
    monkeypatch: pytest.MonkeyPatch, word_count: int
) -> None:
    """Below _LLM_SUMMARY_MIN_WORDS or above MAX => empty => caller falls back."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    summary = _build_in_bounds_summary(word_count) if word_count else ""
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))
    assert build_resume._generate_jd_tailored_summary_via_llm(resume) == ""


def test_generate_jd_tailored_summary_trims_layout_overflow_to_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Word-count in bounds but wrap_lines > 6 => trim instead of reject.

    Issue #282 (policy change): the LLM path previously REJECTED any
    summary that didn't fit the 6-line profile-summary slot, falling
    back to the fully-deterministic generator. In the v4 multi-JD run
    this turned a small (1-line) overflow on llama::becu into a 100%
    loss of LLM tailoring — the deterministic boilerplate is generic.
    The deterministic generator already trims-to-fit via
    `_fit_profile_summary_layout`; the LLM path now applies the same
    trimmer, retaining most of the LLM tailoring. The pre-#282 reject
    behavior is preserved only when trimming chews below the
    `_LLM_SUMMARY_MIN_WORDS` sanity floor (separate test below).
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    summary = _build_layout_overflow_summary(100)  # 100 long tokens
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    # Sanity: word count is in bounds but line count is over at the
    # profile-summary width (NOT the default SUMMARY_LINE_WIDTH).
    assert (
        build_resume._LLM_SUMMARY_MIN_WORDS
        <= 100
        <= build_resume.PROFILE_SUMMARY_MAX_WORDS
    )
    assert (
        len(
            build_resume._summary_wrap_lines(
                summary, line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH
            )
        )
        > build_resume.PROFILE_SUMMARY_MAX_LINES
    )

    out = build_resume._generate_jd_tailored_summary_via_llm(resume)

    # Now the function returns trimmed-but-tailored output rather than "".
    assert out, "expected trimmed LLM summary, got empty (deterministic fallback)"
    assert out.endswith((".", "?", "!"))
    # Trimmed output must fit the 6-line layout cap at the profile width.
    out_lines = build_resume._summary_wrap_lines(
        out, line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH
    )
    assert len(out_lines) <= build_resume.PROFILE_SUMMARY_MAX_LINES
    # And must still be above the LLM-specific min-words floor.
    assert len(out.split()) >= build_resume._LLM_SUMMARY_MIN_WORDS


def test_generate_jd_tailored_summary_falls_back_when_trim_drops_below_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the LLM is wildly over-budget and the trimmer would chew the
    summary below `_LLM_SUMMARY_MIN_WORDS`, fall back to deterministic.

    Issue #282 sanity floor: trimming a small (1-2 line) overflow is
    an obvious win, but if the LLM produced a 12-line summary that
    needs to lose ~70 words to fit 6 lines, the trimmed remainder is
    likely too short to be a useful summary on its own. Better to fall
    back so the deterministic generator produces a complete summary.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    # Construct a summary whose tokens are long enough that trimming to
    # ≤ PROFILE_SUMMARY_MAX_LINES wrapped lines drops the word count
    # below `_LLM_SUMMARY_MIN_WORDS`. Per-line capacity at width 115:
    # roughly `(line_width + 1) // (token_len + 1)` tokens (the `+1`
    # accounts for the inter-token space), so the 6-line trimmed budget
    # is ~6 * (115 + 1) / (len(token) + 1) tokens. With a 32-char token
    # that's ~6 * 116 / 33 ≈ 21 tokens — well below the 30-word floor,
    # forcing the fallback path.
    token = "extremelylongextrasuperlongtoken"  # 32 chars
    assert (
        build_resume.PROFILE_SUMMARY_MAX_LINES
        * (build_resume.PROFILE_SUMMARY_LINE_WIDTH + 1)
        // (len(token) + 1)
        < build_resume._LLM_SUMMARY_MIN_WORDS
    ), "test scaffolding bug: trim budget must be below the min-words floor"
    summary = " ".join([token] * 110)
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    # Sanity: 110 words is in [30, 112]; line count is well over 6.
    assert (
        build_resume._LLM_SUMMARY_MIN_WORDS
        <= 110
        <= build_resume.PROFILE_SUMMARY_MAX_WORDS
    )
    assert (
        len(
            build_resume._summary_wrap_lines(
                summary, line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH
            )
        )
        > build_resume.PROFILE_SUMMARY_MAX_LINES
    )

    out = build_resume._generate_jd_tailored_summary_via_llm(resume)
    # Trimmer output is below the floor → fall back to deterministic ("").
    assert out == ""


def test_generate_jd_tailored_summary_measures_wrap_lines_after_period_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrap-line invariant for the LLM JD-tailored summary path.

    The wrap-line check must run on the post-normalization candidate
    (rstripped + terminal period appended), not on the raw LLM
    response. If the period were added AFTER the wrap-line check, a
    borderline summary that wrapped to exactly 6 lines could become 7
    lines once the period was appended — silently violating
    PROFILE_SUMMARY_MAX_LINES.

    Constructing the exact byte boundary is brittle (depends on
    `textwrap` internals); instead this test exercises the invariant
    directly: regardless of input shape, the returned summary must
    always wrap to ≤ PROFILE_SUMMARY_MAX_LINES at the profile width.
    Multiple inputs are tried so the invariant catches any future
    reordering regression.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    # Inputs that previously could trip the bug: word counts straddling
    # the 6-line cap at width 115, with and without trailing punctuation
    # the rstrip would remove (forcing the period to be appended later).
    inputs = [
        _build_in_bounds_summary(95),  # ~5 lines, well under
        _build_in_bounds_summary(105),  # near the boundary
        _build_in_bounds_summary(105) + ",",  # trailing comma → rstrip → period append
        _build_in_bounds_summary(105) + " ;",  # trailing semicolon
        _build_layout_overflow_summary(100),  # forces trim path
    ]

    for raw_summary in inputs:
        _install_fake_llm(monkeypatch, payload={"summary": raw_summary})
        resume = _minimal_resume_ir(
            job_context=_make_job_context("Real JD body. " * 30)
        )
        out = build_resume._generate_jd_tailored_summary_via_llm(resume)
        # All inputs are in-bounds and either fit the layout or are
        # trim-able to fit (no input here is wildly-over-budget that
        # would force the deterministic fallback). An empty result
        # means a valid LLM summary was unexpectedly rejected — that
        # is the regression this test guards against.
        assert out, (
            f"unexpected deterministic fallback (empty output) for "
            f"in-bounds input {raw_summary!r}"
        )
        wrapped = build_resume._summary_wrap_lines(
            out, line_width=build_resume.PROFILE_SUMMARY_LINE_WIDTH
        )
        assert len(wrapped) <= build_resume.PROFILE_SUMMARY_MAX_LINES, (
            f"output exceeds {build_resume.PROFILE_SUMMARY_MAX_LINES} lines "
            f"({len(wrapped)} lines); input was {raw_summary!r}; output {out!r}"
        )
        # Also assert the output ends with terminal punctuation (the
        # normalization invariant the fix preserves).
        assert out.endswith((".", "?", "!"))


def test_generate_jd_tailored_summary_returns_empty_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive: helper short-circuits when LLM gating is off.

    Issue #256 round-1 review — docstring promised this behavior but
    the function previously didn't check _llm_stage_enabled() itself
    (the gate lived in summarize_profile_for_role's caller path).
    Now it's explicit so the helper is safe to call from anywhere.
    """
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)

    def fail_if_called() -> Any:
        raise AssertionError(
            "LLMClient.from_env should not be called when LLM is disabled"
        )

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env", fail_if_called
    )
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))
    assert build_resume._generate_jd_tailored_summary_via_llm(resume) == ""


def test_generate_jd_tailored_summary_returns_empty_when_llm_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    _install_fake_llm(monkeypatch, raise_on_call=RuntimeError("network down"))
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))
    assert build_resume._generate_jd_tailored_summary_via_llm(resume) == ""


def test_generate_jd_tailored_summary_returns_empty_when_no_job_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No JD context => helper short-circuits without invoking LLM."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    resume = _minimal_resume_ir(job_context=None)
    # No mock needed: the function returns early before LLMClient touch.
    assert build_resume._generate_jd_tailored_summary_via_llm(resume) == ""


def test_summarize_profile_for_role_uses_llm_summary_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: LLM enabled + substantive JD => profile.summary swapped."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    summary = _build_in_bounds_summary(100)  # in [90, 112], fits 6 lines @ 115
    _install_fake_llm(monkeypatch, payload={"summary": summary})
    resume = _minimal_resume_ir(
        summary="Original deterministic baseline.",
        job_context=_make_job_context("Real JD body. " * 30),
    )

    out = build_resume.summarize_profile_for_role(resume)

    assert out.profile.summary != "Original deterministic baseline."
    assert out.profile.summary.startswith("word word")
    assert out.profile.summary.endswith(".")


def test_summarize_profile_for_role_falls_back_to_deterministic_on_llm_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM enabled + LLM returns empty => deterministic generator runs."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    _install_fake_llm(monkeypatch, payload={"summary": ""})
    captured: dict[str, bool] = {"called": False}

    real_generate = build_resume._generate_profile_summary

    def spy(resume: build_resume.ResumeIR) -> str:
        captured["called"] = True
        return real_generate(resume)

    monkeypatch.setattr(build_resume, "_generate_profile_summary", spy)
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    build_resume.summarize_profile_for_role(resume)

    assert captured["called"] is True


def test_summarize_profile_for_role_skips_llm_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM disabled => helper never even constructs an LLMClient."""
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)

    def fail_if_called() -> Any:
        raise AssertionError("LLMClient.from_env should not be called")

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env", fail_if_called
    )
    resume = _minimal_resume_ir(job_context=_make_job_context("Real JD body. " * 30))

    build_resume.summarize_profile_for_role(resume)


def test_summarize_profile_for_role_skips_llm_when_jd_context_thin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Substantive JD threshold not met => helper never constructs LLMClient."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called() -> Any:
        raise AssertionError("LLMClient.from_env should not be called")

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env", fail_if_called
    )
    resume = _minimal_resume_ir(
        job_context=_make_job_context("A" * 100)  # under 200-char threshold
    )
    build_resume.summarize_profile_for_role(resume)


# ---------------------------------------------------------------------------
# --fit-narrative CLI validation + fit_assessment plumbing (issue #272)
# ---------------------------------------------------------------------------


def test_parse_fit_narrative_mode_accepts_valid_values() -> None:
    assert build_resume._parse_fit_narrative_mode("auto") == "auto"
    assert build_resume._parse_fit_narrative_mode("on") == "on"
    assert build_resume._parse_fit_narrative_mode("off") == "off"


def test_parse_fit_narrative_mode_is_case_insensitive() -> None:
    assert build_resume._parse_fit_narrative_mode("Auto") == "auto"
    assert build_resume._parse_fit_narrative_mode("OFF") == "off"


def test_parse_fit_narrative_mode_rejects_unknown_values() -> None:
    import argparse as _argparse

    with pytest.raises(_argparse.ArgumentTypeError, match="must be one of"):
        build_resume._parse_fit_narrative_mode("yes")
    with pytest.raises(_argparse.ArgumentTypeError, match="must be one of"):
        build_resume._parse_fit_narrative_mode("")


# Helpers ---------------------------------------------------------------------


def _substantive_jd_excerpt() -> str:
    """JD excerpt comfortably above _MIN_JD_DESCRIPTION_CHARS (200)."""
    return (
        "Lead testing strategy for distributed payments systems. "
        "Drive automation across services. Partner with developers on "
        "reliability, observability, and CI/CD. Review and mentor engineers "
        "on test design and framework architecture decisions."
    ) * 2


def _resume_with_one_experience() -> build_resume.ResumeIR:
    """ResumeIR with one experience (id=exp-1) and a substantive JD context."""
    base = _minimal_resume_ir(job_context=_make_job_context(_substantive_jd_excerpt()))
    experience = build_resume.Experience(
        id="exp-1",
        job_title="Senior SDET",
        company="ExampleCo",
        start_date="2020-01",
        end_date="present",
        general_role_description="Test platform engineering.",
        related_skills=("Python", "Pytest"),
        bullets=(
            build_resume.Bullet(
                id="b-1",
                text="Built CI pipelines.",
                skills=("Python",),
                impact_type="",
                domain="",
            ),
        ),
    )
    return dataclasses.replace(base, experiences=(experience,))


class _FakeLLMClient:
    """Minimal stand-in for LLMClient in tests."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self, *, namespace: str, system_prompt: str, user_payload: dict[str, object]
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "namespace": namespace,
                "system_prompt": system_prompt,
                "user_payload": user_payload,
            }
        )
        return self._response


# compute_fit_assessment ------------------------------------------------------


def test_compute_fit_assessment_returns_none_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    assert build_resume.compute_fit_assessment(_resume_with_one_experience()) is None


def test_compute_fit_assessment_returns_none_when_jd_context_thin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    resume = _resume_with_one_experience()
    thin_resume = dataclasses.replace(resume, job_context=_make_job_context("short"))
    assert build_resume.compute_fit_assessment(thin_resume) is None


def test_compute_fit_assessment_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 42,
            "overall_rationale": "domain mismatch",
            "per_experience_scores": [
                {
                    "experience_id": "exp-1",
                    "fit_score": 55,
                    "rationale": "partial overlap",
                },
            ],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    assessment = build_resume.compute_fit_assessment(_resume_with_one_experience())

    assert assessment is not None
    assert assessment.overall_fit_score == 42.0
    assert assessment.overall_rationale == "domain mismatch"
    assert len(assessment.per_experience_scores) == 1
    assert assessment.per_experience_scores[0].experience_id == "exp-1"
    assert assessment.per_experience_scores[0].fit_score == 55.0
    # Single LLM call routed through the dedicated namespace for caching.
    assert fake.calls and fake.calls[0]["namespace"] == "fit_assessment"


def test_compute_fit_assessment_prompt_calibrates_for_context_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #303 calibration: the fit_assessment system prompt must spell
    out the context-vs-skill rubric and ground it in ICL examples so a
    test-automation candidate applying to a backend-dev JD scores as a
    stretch even when the resume shares Java / Spring vocabulary with the
    JD. Locking the rubric language in the prompt keeps the calibration
    from silently regressing during future prompt edits.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 35,
            "overall_rationale": "context mismatch",
            "per_experience_scores": [
                {
                    "experience_id": "exp-1",
                    "fit_score": 35,
                    "rationale": "shared skills, different context",
                },
            ],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    build_resume.compute_fit_assessment(_resume_with_one_experience())

    assert fake.calls
    prompt = fake.calls[0]["system_prompt"]
    # Rubric: identify and compare CONTEXTS (not just skills).
    assert "CONTEXT" in prompt
    assert "RUBRIC" in prompt
    # Skill-vs-context distinction is explicit.
    assert "SKILLS overlap" in prompt or "SKILLS" in prompt
    # Anti-hallucination guardrail must be explicit so smaller models stop
    # crediting the candidate with JD-named skills the resume doesn't show
    # (v10 calibration finding — gemma 9b false-positive on Spring Boot).
    assert "ANTI-HALLUCINATION" in prompt
    assert "verbatim" in prompt or "near-paraphrase" in prompt
    # Rationale shape requirement so cover-letter bridging has concrete
    # CONTEXT names to ground its template.
    assert "RATIONALE SHAPE" in prompt
    # ICL examples cover BOTH stretch directions AND a matched-context
    # positive anchor — without the positive anchor, calibration leans
    # too heavily into stretch (v10 finding on BECU).
    assert "EXAMPLES" in prompt
    assert "matched context" in prompt
    assert "SDET" in prompt
    assert "Backend Dev" in prompt


def test_compute_fit_assessment_rejects_out_of_range_overall_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 150,  # out of 0-100 range
            "overall_rationale": "ok",
            "per_experience_scores": [],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    assert build_resume.compute_fit_assessment(_resume_with_one_experience()) is None


def test_coerce_fit_score_accepts_valid_numbers() -> None:
    assert build_resume._coerce_fit_score(0) == 0.0
    assert build_resume._coerce_fit_score(50) == 50.0
    assert build_resume._coerce_fit_score(100.0) == 100.0
    assert build_resume._coerce_fit_score("42") == 42.0


def test_coerce_fit_score_rejects_unusable_inputs() -> None:
    # Booleans look numeric to ``float()`` (True -> 1.0, False -> 0.0); a
    # malformed LLM payload like ``true`` must not silently become a real
    # score (PR #278 review).
    assert build_resume._coerce_fit_score(True) is None
    assert build_resume._coerce_fit_score(False) is None
    assert build_resume._coerce_fit_score(None) is None
    assert build_resume._coerce_fit_score("nope") is None
    assert build_resume._coerce_fit_score(float("nan")) is None
    assert build_resume._coerce_fit_score(float("inf")) is None
    assert build_resume._coerce_fit_score(-1) is None
    assert build_resume._coerce_fit_score(101) is None


def test_compute_fit_assessment_drops_unknown_experience_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 30,
            "overall_rationale": "stretch",
            "per_experience_scores": [
                {"experience_id": "exp-1", "fit_score": 40, "rationale": "ok"},
                {"experience_id": "ghost-id", "fit_score": 90, "rationale": "x"},
            ],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    assessment = build_resume.compute_fit_assessment(_resume_with_one_experience())

    assert assessment is not None
    assert {entry.experience_id for entry in assessment.per_experience_scores} == {
        "exp-1"
    }


def test_compute_fit_assessment_rejects_payload_missing_known_experience_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The prompt asks for one entry per input experience and #271 will use
    this mapping for compression; caching a partial set would silently
    miscompress, so a missing known experience_id rejects the payload."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 30,
            "overall_rationale": "stretch",
            "per_experience_scores": [],  # exp-1 is known but absent
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    assert build_resume.compute_fit_assessment(_resume_with_one_experience()) is None


def test_compute_fit_assessment_omits_current_level_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirror the jd_tailored_summary cache-key fix: candidate_current_level
    must NOT appear in the fit_assessment user_payload when unset
    (PR #278 review — avoid cache fragmentation)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 50,
            "overall_rationale": "ok",
            "per_experience_scores": [
                {"experience_id": "exp-1", "fit_score": 50, "rationale": "ok"},
            ],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    resume = _resume_with_one_experience()
    assert resume.profile.current_level == ""
    build_resume.compute_fit_assessment(resume)
    assert fake.calls
    assert "candidate_current_level" not in fake.calls[0]["user_payload"]


def test_compute_fit_assessment_includes_current_level_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 50,
            "overall_rationale": "ok",
            "per_experience_scores": [
                {"experience_id": "exp-1", "fit_score": 50, "rationale": "ok"},
            ],
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    base = _resume_with_one_experience()
    profile = dataclasses.replace(base.profile, current_level="Senior Staff Engineer")
    resume = dataclasses.replace(base, profile=profile)
    build_resume.compute_fit_assessment(resume)
    assert fake.calls
    assert (
        fake.calls[0]["user_payload"]["candidate_current_level"]
        == "Senior Staff Engineer"
    )


def test_compute_fit_assessment_returns_none_on_llm_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    class _BoomClient:
        def complete_json(self, **_kwargs: object) -> dict[str, Any]:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "resume_builder.build_resume.LLMClient.from_env", lambda: _BoomClient()
    )

    assert build_resume.compute_fit_assessment(_resume_with_one_experience()) is None


# _resolve_fit_narrative ------------------------------------------------------


def _ns(**kwargs: object) -> argparse.Namespace:
    """Tiny helper to build an argparse Namespace for resolver tests."""
    defaults: dict[str, object] = {"fit_narrative": "auto", "cover_letter": False}
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def test_resolve_fit_narrative_off_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called(_resume: Any) -> Any:
        raise AssertionError("compute_fit_assessment should not be called")

    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", fail_if_called
    )
    caplog.set_level(logging.INFO, logger="resume_builder.build_resume")
    assert (
        build_resume._resolve_fit_narrative(
            _ns(fit_narrative="off"), _resume_with_one_experience()
        )
        is None
    )
    # Off path now logs at INFO so debugging stays consistent with the
    # other skip paths (PR #278 review).
    assert any(
        "fit_narrative skipped: --fit-narrative off" in record.getMessage()
        for record in caplog.records
    )


def test_resolve_fit_narrative_normalizes_uppercase_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Programmatic callers may pass un-normalized values; resolver should
    canonicalize so 'OFF' still hits the off branch (PR #278 review)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called(_resume: Any) -> Any:
        raise AssertionError("compute_fit_assessment should not be called")

    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", fail_if_called
    )
    assert (
        build_resume._resolve_fit_narrative(
            _ns(fit_narrative="OFF"), _resume_with_one_experience()
        )
        is None
    )


def test_resolve_fit_narrative_coerces_unknown_mode_to_auto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected programmatic values fall back to 'auto' rather than
    silently bypassing the auto-mode gates (PR #278 review)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called(_resume: Any) -> Any:
        raise AssertionError("auto-mode + cover-letter must skip the LLM call")

    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", fail_if_called
    )
    # Auto-mode skips when cover_letter is set; using cover_letter=True lets
    # us confirm the unknown 'bogus' value was coerced into auto's behavior.
    result = build_resume._resolve_fit_narrative(
        _ns(fit_narrative="bogus", cover_letter=True),
        _resume_with_one_experience(),
    )
    assert result is None


def test_resolve_fit_narrative_auto_defers_to_cover_letter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called(_resume: Any) -> Any:
        raise AssertionError("cover-letter path must skip the LLM call")

    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", fail_if_called
    )
    assert (
        build_resume._resolve_fit_narrative(
            _ns(fit_narrative="auto", cover_letter=True),
            _resume_with_one_experience(),
        )
        is None
    )


def test_resolve_fit_narrative_skips_when_llm_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    assert (
        build_resume._resolve_fit_narrative(_ns(), _resume_with_one_experience())
        is None
    )


def test_resolve_fit_narrative_skips_when_jd_context_thin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    thin_resume = dataclasses.replace(
        _resume_with_one_experience(), job_context=_make_job_context("short")
    )
    assert build_resume._resolve_fit_narrative(_ns(), thin_resume) is None


def test_resolve_fit_narrative_auto_skips_when_score_at_or_above_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment",
        lambda _resume: build_resume.FitAssessment(
            overall_fit_score=75.0,
            overall_rationale="strong fit",
            per_experience_scores=(),
        ),
    )
    assert (
        build_resume._resolve_fit_narrative(_ns(), _resume_with_one_experience())
        is None
    )


def test_resolve_fit_narrative_auto_fires_below_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    expected = build_resume.FitAssessment(
        overall_fit_score=42.0,
        overall_rationale="domain mismatch",
        per_experience_scores=(),
    )
    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", lambda _resume: expected
    )
    result = build_resume._resolve_fit_narrative(_ns(), _resume_with_one_experience())
    assert result is expected


def test_resolve_fit_narrative_on_bypasses_score_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    expected = build_resume.FitAssessment(
        overall_fit_score=95.0,  # well above gate; auto would skip, on must fire
        overall_rationale="strong fit",
        per_experience_scores=(),
    )
    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", lambda _resume: expected
    )
    result = build_resume._resolve_fit_narrative(
        _ns(fit_narrative="on"), _resume_with_one_experience()
    )
    assert result is expected


# Summary augmentation --------------------------------------------------------


def test_jd_tailored_summary_augmented_when_fit_assessment_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When fit_assessment is passed in, the system prompt asks for the
    fit-narrative clause and the user payload carries the rationale.
    """
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "summary": (
                "Senior test engineer with deep experience in distributed "
                "systems testing, payments reliability, and CI/CD automation, "
                "delivering measurable defect reductions and shipping framework "
                "improvements that scale across teams of 50+ engineers as a "
                "domain-adjacent fit translating QA-leadership signal into "
                "this role's developer-tooling responsibilities."
            )
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    assessment = build_resume.FitAssessment(
        overall_fit_score=45.0,
        overall_rationale="QA -> developer tooling shift",
        per_experience_scores=(),
    )
    result = build_resume._generate_jd_tailored_summary_via_llm(
        _resume_with_one_experience(), fit_assessment=assessment
    )

    assert result  # not empty (passed bounds + layout guards)
    assert fake.calls
    call = fake.calls[0]
    # Augmentation references the rationale + score keys and frames the
    # clause neutrally so --fit-narrative on against a high-fit JD does
    # not force a "stretch" framing.
    assert "fit-narrative clause" in call["system_prompt"]
    assert "fit_narrative_rationale" in call["system_prompt"]
    assert "fit_narrative_overall_score" in call["system_prompt"]
    assert call["user_payload"]["fit_narrative_rationale"] == (
        "QA -> developer tooling shift"
    )
    assert call["user_payload"]["fit_narrative_overall_score"] == 45.0


def test_jd_tailored_summary_omits_current_level_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """current_level must NOT appear in the user_payload when unset, so
    profiles that don't supply it keep the same LLM cache key as before
    #272 landed (PR #278 review — avoid cache-key churn / extra tokens)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "summary": (
                "Senior test engineer with deep experience across distributed "
                "payments systems, automation pipelines, observability tooling, "
                "and CI/CD scaling for engineering teams. Delivered measurable "
                "reliability improvements, drove test framework redesigns, and "
                "mentored peer engineers on long-horizon test architecture and "
                "release cadence decisions."
            )
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    resume = _resume_with_one_experience()
    # Default profile has current_level = "" (empty).
    assert resume.profile.current_level == ""
    build_resume._generate_jd_tailored_summary_via_llm(resume)
    assert fake.calls
    assert "candidate_current_level" not in fake.calls[0]["user_payload"]


def test_jd_tailored_summary_includes_current_level_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the user supplies current_level, it lands in the payload and the
    prompt references it so the LLM can frame seniority correctly."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "summary": (
                "Senior test engineer with deep experience across distributed "
                "payments systems, automation pipelines, observability tooling, "
                "and CI/CD scaling for engineering teams. Delivered measurable "
                "reliability improvements, drove test framework redesigns, and "
                "mentored peer engineers on long-horizon test architecture and "
                "release cadence decisions."
            )
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    base = _resume_with_one_experience()
    profile = dataclasses.replace(base.profile, current_level="Senior Staff Engineer")
    resume = dataclasses.replace(base, profile=profile)
    build_resume._generate_jd_tailored_summary_via_llm(resume)
    assert fake.calls
    call = fake.calls[0]
    assert call["user_payload"]["candidate_current_level"] == "Senior Staff Engineer"
    assert "candidate_current_level" in call["system_prompt"]


def test_jd_tailored_summary_unchanged_when_no_fit_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No augmentation when fit_assessment is None (default behavior)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    fake = _FakeLLMClient(
        {
            "summary": (
                "Senior test engineer with deep experience across distributed "
                "payments systems, automation pipelines, observability tooling, "
                "and CI/CD scaling for engineering teams. Delivered measurable "
                "reliability improvements, drove test framework redesigns, and "
                "mentored peer engineers on long-horizon test architecture and "
                "release cadence decisions."
            )
        }
    )
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    result = build_resume._generate_jd_tailored_summary_via_llm(
        _resume_with_one_experience()
    )

    assert result
    assert fake.calls
    call = fake.calls[0]
    assert "fit-narrative clause" not in call["system_prompt"]
    assert "fit_narrative_rationale" not in call["user_payload"]
    assert "fit_narrative_overall_score" not in call["user_payload"]


def test_resolve_fit_narrative_payload_reflects_caller_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for PR #278 review: the LLM payload's bullets reflect
    whatever resume the caller passes. The pipeline call site is expected
    to pass the pre-pipeline ``baseline_resume`` so the LLM sees the
    candidate's full canonical bullet set, not the post-trim view.

    Demonstrates the contract by calling against (a) a synthetic post-trim
    view with empty bullets and (b) the baseline with full bullets, and
    confirming the LLM payload differs as expected.
    """
    fake = _FakeLLMClient(
        {
            "overall_fit_score": 30,
            "overall_rationale": "stretch",
            "per_experience_scores": [
                {"experience_id": "exp-1", "fit_score": 40, "rationale": "ok"},
            ],
        }
    )
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")
    monkeypatch.setattr("resume_builder.build_resume.LLMClient.from_env", lambda: fake)

    baseline = _resume_with_one_experience()
    trimmed = dataclasses.replace(
        baseline,
        experiences=tuple(
            dataclasses.replace(exp, bullets=()) for exp in baseline.experiences
        ),
    )

    # Calling against the trimmed view: empty bullets reach the LLM.
    build_resume._resolve_fit_narrative(_ns(), trimmed)
    assert fake.calls
    trimmed_payload: Any = fake.calls[-1]["user_payload"]["experiences"]
    assert isinstance(trimmed_payload, list) and trimmed_payload
    assert trimmed_payload[0]["bullets"] == []

    # Calling against the baseline: full bullet set reaches the LLM —
    # this is what the pipeline call site does post-fix.
    build_resume._resolve_fit_narrative(_ns(), baseline)
    baseline_payload: Any = fake.calls[-1]["user_payload"]["experiences"]
    assert isinstance(baseline_payload, list) and baseline_payload
    assert baseline_payload[0]["bullets"] == ["Built CI pipelines."]


# current_level profile.toml integration --------------------------------------


def test_load_experiences_rejects_empty_id(tmp_path: Path) -> None:
    """experience_db.toml must reject empty ids — apply_experience_compression
    tracks experiences by id and an empty/duplicate id would silently bucket
    multiple roles together (PR #278 review)."""
    db = tmp_path / "experience_db.toml"
    db.write_text(
        """
[[experience]]
id = ""
job_title = "Senior SDET"
company = "ExampleCo"
start_date = "2020-01"
end_date = "present"
general_role_description = "Test platform engineering."
related_skills = ["Python"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="non-empty id"):
        build_resume.load_experiences(db)


def test_load_experiences_rejects_duplicate_ids(tmp_path: Path) -> None:
    db = tmp_path / "experience_db.toml"
    db.write_text(
        """
[[experience]]
id = "exp-1"
job_title = "Senior SDET"
company = "ExampleCo"
start_date = "2020-01"
end_date = "present"
general_role_description = "Test platform engineering."
related_skills = ["Python"]

[[experience]]
id = "exp-1"
job_title = "Senior SDET"
company = "OtherCo"
start_date = "2018-01"
end_date = "2019-12"
general_role_description = "Test platform engineering."
related_skills = ["Python"]
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be unique"):
        build_resume.load_experiences(db)


def test_resolve_fit_narrative_accepts_precomputed_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipeline computes fit_assessment once and feeds the resolver, so the
    resolver must NOT call compute_fit_assessment again when an assessment
    is supplied (PR #278 review — avoid double LLM round-trips on exception
    paths)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    def fail_if_called(_resume: Any) -> Any:
        raise AssertionError(
            "compute_fit_assessment must not run when assessment is precomputed"
        )

    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", fail_if_called
    )

    expected = build_resume.FitAssessment(
        overall_fit_score=42.0,
        overall_rationale="domain mismatch",
        per_experience_scores=(),
    )
    result = build_resume._resolve_fit_narrative(
        _ns(), _resume_with_one_experience(), fit_assessment=expected
    )
    assert result is expected


def test_resolve_fit_narrative_back_compat_computes_when_not_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing callers that don't pass fit_assessment still trigger an
    internal compute_fit_assessment call (back-compat)."""
    monkeypatch.setenv("RESUME_BUILDER_LLM_ENABLED", "1")

    expected = build_resume.FitAssessment(
        overall_fit_score=42.0,
        overall_rationale="domain mismatch",
        per_experience_scores=(),
    )
    monkeypatch.setattr(
        "resume_builder.build_resume.compute_fit_assessment", lambda _resume: expected
    )
    result = build_resume._resolve_fit_narrative(_ns(), _resume_with_one_experience())
    assert result is expected


def test_render_html_compressed_experience_omits_role_summary_and_related(
    tmp_path: Path,
) -> None:
    """HTML render must mirror markdown's compressed-mode behavior: title
    + dates + single bullet only, with role-summary and related-skills
    blocks suppressed (PR #278 review)."""
    base = _resume_with_one_experience()
    compressed_exp = dataclasses.replace(base.experiences[0], compression="compressed")
    resume = dataclasses.replace(base, experiences=(compressed_exp,))
    output = tmp_path / "resume.html"
    build_resume.render_html(resume, output)
    content = output.read_text(encoding="utf-8")
    assert "Senior SDET" in content
    assert "Built CI pipelines." in content
    # Compressed: role-summary and related-skills paragraphs must NOT render.
    assert 'class="role-summary"' not in content
    assert 'class="related-skills"' not in content
    # Exactly one bullet, not two.
    assert content.count("<li>") == 1


def test_render_html_full_experience_keeps_role_summary_and_related(
    tmp_path: Path,
) -> None:
    """Sanity counterpart: full-mode HTML still renders role-summary and
    related-skills."""
    resume = _resume_with_one_experience()
    output = tmp_path / "resume.html"
    build_resume.render_html(resume, output)
    content = output.read_text(encoding="utf-8")
    assert 'class="role-summary"' in content
    assert "Test platform engineering." in content


def test_load_profile_accepts_optional_current_level(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Test User"
headline = ""
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = ""
current_level = "Senior Staff Engineer"
""",
        encoding="utf-8",
    )

    profile = build_resume.load_profile(profile_path)
    assert profile.current_level == "Senior Staff Engineer"


def test_load_profile_defaults_current_level_to_empty(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Test User"
headline = ""
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = ""
""",
        encoding="utf-8",
    )

    profile = build_resume.load_profile(profile_path)
    assert profile.current_level == ""


# ---------------------------------------------------------------------------
# --experience-mode CLI validation + apply_experience_compression (issue #271)
# ---------------------------------------------------------------------------


def test_parse_experience_mode_accepts_canonical_values() -> None:
    assert build_resume._parse_experience_mode("auto") == "auto"
    assert build_resume._parse_experience_mode("all") == "all"
    assert build_resume._parse_experience_mode("top-5") == "top-5"
    assert build_resume._parse_experience_mode("Top-12") == "top-12"


def test_parse_experience_mode_rejects_garbage() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="must be"):
        build_resume._parse_experience_mode("top-0")
    with pytest.raises(argparse.ArgumentTypeError, match="must be"):
        build_resume._parse_experience_mode("top-N")
    with pytest.raises(argparse.ArgumentTypeError, match="must be"):
        build_resume._parse_experience_mode("nonsense")


def test_experience_mode_top_n_extracts_int() -> None:
    assert build_resume._experience_mode_top_n("top-5") == 5
    assert build_resume._experience_mode_top_n("top-12") == 12
    assert build_resume._experience_mode_top_n("auto") is None
    assert build_resume._experience_mode_top_n("all") is None


def _resume_with_n_experiences(n: int) -> build_resume.ResumeIR:
    """Build a resume with n distinct experience entries against a substantive JD."""
    base = _resume_with_one_experience()
    experiences = []
    for i in range(n):
        exp = build_resume.Experience(
            id=f"exp-{i + 1}",
            job_title=f"Senior SDET {i + 1}",
            company="ExampleCo",
            start_date="2020-01",
            end_date="present",
            general_role_description="Test platform engineering.",
            related_skills=("Python",),
            bullets=(
                build_resume.Bullet(
                    id=f"b-{i + 1}-1",
                    text=f"Bullet text {i + 1}.A.",
                    skills=("Python",),
                    impact_type="",
                    domain="",
                ),
                build_resume.Bullet(
                    id=f"b-{i + 1}-2",
                    text=f"Bullet text {i + 1}.B.",
                    skills=("Python",),
                    impact_type="",
                    domain="",
                ),
            ),
        )
        experiences.append(exp)
    return dataclasses.replace(base, experiences=tuple(experiences))


def _experience_mode_args(mode: str) -> argparse.Namespace:
    return argparse.Namespace(experience_mode=mode)


def test_apply_experience_compression_all_mode_is_noop() -> None:
    resume = _resume_with_n_experiences(4)
    result = build_resume.apply_experience_compression(
        _experience_mode_args("all"), resume, fit_assessment=None
    )
    assert result is resume
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_no_context_forces_all() -> None:
    base = _resume_with_n_experiences(4)
    # Drop JD context below the substantive-content threshold.
    thin = dataclasses.replace(base, job_context=_make_job_context(""))
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-1"), thin, fit_assessment=None
    )
    # No-context fallback forces 'all' regardless of flag.
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_top_n_marks_beyond_rank() -> None:
    resume = _resume_with_n_experiences(4)
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-2"), resume, fit_assessment=None
    )
    # First 2 stay full; remaining 2 compressed (within the 50% cap).
    assert result.experiences[0].compression == "full"
    assert result.experiences[1].compression == "full"
    assert result.experiences[2].compression == "compressed"
    assert result.experiences[3].compression == "compressed"


def test_apply_experience_compression_top_n_respects_50pct_cap() -> None:
    resume = _resume_with_n_experiences(4)
    # top-1 would compress 3 of 4 (exp-2..exp-4), but the 50% cap (= 2)
    # stops at 2. The cap must compress the *worst* of the demoted group —
    # exp-3 and exp-4 — not the top of beyond-N (PR #278 review). exp-2
    # stays full because it's the most relevant of the demoted group.
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-1"), resume, fit_assessment=None
    )
    compressed_ids = {
        exp.id for exp in result.experiences if exp.compression == "compressed"
    }
    assert compressed_ids == {"exp-3", "exp-4"}


def test_apply_experience_compression_all_resets_pre_existing_compressed() -> None:
    """all-mode contract is 'every experience full' — must override any
    pre-existing compressed marker (PR #278 review)."""
    base = _resume_with_n_experiences(3)
    pre_marked = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, compression="compressed")
            for exp in base.experiences
        ),
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("all"), pre_marked, fit_assessment=None
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_no_context_resets_pre_existing_compressed() -> (
    None
):
    """No-context fallback also resets pre-existing compression so a stale
    marker from an earlier pass doesn't reach the renderer (PR #278 review)."""
    base = _resume_with_n_experiences(3)
    base = dataclasses.replace(base, job_context=_make_job_context(""))
    pre_marked = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, compression="compressed")
            for exp in base.experiences
        ),
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-1"), pre_marked, fit_assessment=None
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_render_html_skips_empty_role_summary_paragraph(tmp_path: Path) -> None:
    """Full-mode render must NOT emit `<p class="role-summary"></p>` when
    the description is empty/whitespace — otherwise the renderer disagrees
    with `_compute_bullet_line_budget`'s round-11 zero-cost credit and
    auto-compression would under-budget vs the actual layout
    (PR #278 review)."""
    base = _resume_with_one_experience()
    cleared = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, general_role_description="")
            for exp in base.experiences
        ),
    )
    output = tmp_path / "resume.html"
    build_resume.render_html(cleared, output)
    content = output.read_text(encoding="utf-8")
    assert 'class="role-summary"' not in content


def test_render_markdown_skips_empty_role_summary_block(tmp_path: Path) -> None:
    """Same suppression in markdown so both renderers stay consistent
    with the budget (PR #278 review)."""
    base = _resume_with_one_experience()
    cleared = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, general_role_description="")
            for exp in base.experiences
        ),
    )
    output = tmp_path / "resume.md"
    build_resume.render_markdown(cleared, output)
    content = output.read_text(encoding="utf-8")
    # No empty-paragraph block (would surface as a stray blank line between
    # the date line and either related-skills or the first bullet).
    # Easiest invariant: the rendered text never contains a "  \n\n\n"
    # pattern from a blank-then-blank-then-blank sequence at the role spot.
    assert "Test platform engineering." not in content  # description is empty
    # The bullet must still render so the experience block isn't a stub.
    assert "Built CI pipelines." in content


def test_apply_experience_compression_skips_bulletless_experiences() -> None:
    """An experience with no bullets cannot satisfy the compressed-mode
    contract (single highest-relevance bullet). The stage must keep such
    experiences in full mode regardless of flag (PR #278 review)."""
    base = _resume_with_n_experiences(3)
    bulletless = build_resume.Experience(
        id="exp-empty",
        job_title="Brief Engagement",
        company="ExampleCo",
        start_date="2019-01",
        end_date="2019-06",
        general_role_description="One-line role description.",
        related_skills=("Python",),
        bullets=(),  # no bullets — cannot honor the compressed-mode contract
    )
    resume = dataclasses.replace(base, experiences=base.experiences + (bulletless,))
    # top-1 → max_compressible = 2; without the filter, exp-empty would
    # be one of the candidates and could be marked compressed. With the
    # filter, exp-empty is excluded; the next-worst bullet-bearing
    # experience compresses instead.
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-1"), resume, fit_assessment=None
    )
    by_id = {exp.id: exp for exp in result.experiences}
    assert by_id["exp-empty"].compression == "full"


def test_apply_experience_compression_top_n_boundary_against_visible_roles() -> None:
    """top-N's boundary is computed against the full visible-roles list, not
    the bullet-bearing-filtered list. A bullet-less role in the first N
    positions still consumes one of the top-N slots — issue #299.

    Setup: 4 visible experiences where the first is bullet-less and the
    other three carry bullets. Under `top-2`:
    - exp-1 (bullet-less, in top-2) stays full (can't compress anyway, but
      it's also one of the kept top-2 visible roles).
    - exp-2 (bullet-bearing, in top-2) stays full (kept).
    - exp-3 and exp-4 are beyond top-2 and have bullets → both compress
      (the 50% cap on 4 visible experiences allows up to 2).

    Pre-fix behavior would have skewed the slice by one bullet-less role
    in the prefix and only compressed exp-4.
    """
    bulletless = build_resume.Experience(
        id="exp-1",
        job_title="Junior Tester",
        company="OldCo",
        start_date="2024-01",
        end_date="2024-06",
        general_role_description="Brief stint.",
        related_skills=("Python",),
        bullets=(),
    )
    base = _resume_with_n_experiences(3)
    # _resume_with_n_experiences gives exp-1..exp-3 by default; rename them
    # to slot the bullet-less first while preserving stable ordering.
    renamed = []
    for offset, exp in enumerate(base.experiences):
        renamed_exp = dataclasses.replace(exp, id=f"exp-{offset + 2}")
        renamed_bullets = tuple(
            dataclasses.replace(b, id=f"b-{offset + 2}-{bidx}")
            for bidx, b in enumerate(exp.bullets, start=1)
        )
        renamed.append(dataclasses.replace(renamed_exp, bullets=renamed_bullets))
    resume = dataclasses.replace(base, experiences=(bulletless,) + tuple(renamed))

    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-2"), resume, fit_assessment=None
    )
    by_id = {exp.id: exp.compression for exp in result.experiences}
    assert by_id == {
        "exp-1": "full",  # bullet-less, in top-2
        "exp-2": "full",  # bullet-bearing, in top-2
        "exp-3": "compressed",  # beyond top-2, bullet-bearing
        "exp-4": "compressed",  # beyond top-2, bullet-bearing
    }


def test_compute_bullet_line_budget_credits_empty_role_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An experience with empty general_role_description must NOT cost a
    role-summary line in the budget. Without this guard
    _estimate_wrapped_line_count("") returns 1 and apply_experience_
    compression's auto-mode simulation can't actually credit the freed
    space (PR #278 review).

    Lift the DEFAULT_MAX_BULLET_LINES cap during this assertion so the
    cap doesn't mask the credit on small fixture resumes (the production
    cap clamps both budgets to the same value when there's plenty of
    headroom).
    """
    monkeypatch.setattr("resume_builder.build_resume.DEFAULT_MAX_BULLET_LINES", 10_000)
    base = _resume_with_n_experiences(2)
    cleared = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, general_role_description="")
            for exp in base.experiences
        ),
    )
    full_budget = build_resume._compute_bullet_line_budget(base)
    cleared_budget = build_resume._compute_bullet_line_budget(cleared)
    # Cleared description -> more bullet-line budget available. Without the
    # fix, both budgets would be equal because empty text counts as 1 line.
    assert cleared_budget > full_budget


def test_apply_experience_compression_auto_resets_stale_compression_when_nothing_to_compress() -> (
    None
):
    """auto-mode that decides nothing should compress (because layout fits)
    must still reset any pre-existing 'compressed' markers — without the
    reset, stale markers from a prior pass would silently survive
    (PR #278 review)."""
    # Tiny resume; layout-fit budget will easily accommodate it.
    base = _resume_with_n_experiences(2)
    pre_marked = dataclasses.replace(
        base,
        experiences=tuple(
            dataclasses.replace(exp, compression="compressed")
            for exp in base.experiences
        ),
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("auto"), pre_marked, fit_assessment=None
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_top_n_resets_stale_when_cap_floor_zero() -> None:
    """top-N early return (max_compressible == 0 because of floor on small
    inputs) must still reset stale compression markers (PR #278 review)."""
    base = _resume_with_n_experiences(1)  # 50% of 1 = 0 → cap floors to 0
    pre_marked = dataclasses.replace(
        base,
        experiences=(
            dataclasses.replace(base.experiences[0], compression="compressed"),
        ),
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-0"),  # bypass CLI validator
        pre_marked,
        fit_assessment=None,
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_fit_assessment_will_be_consumed_off_and_all_returns_false() -> None:
    """No consumer when fit-narrative is off AND experience-mode is all —
    pipeline can skip the LLM round-trip entirely (PR #278 review)."""
    args = argparse.Namespace(
        fit_narrative="off", experience_mode="all", cover_letter=False
    )
    assert build_resume._fit_assessment_will_be_consumed(args) is False


def test_fit_assessment_will_be_consumed_on_with_all_still_returns_true() -> None:
    """fit-narrative on always wants the assessment, even if experience-mode
    is all (the narrative augmentation is still in play)."""
    args = argparse.Namespace(
        fit_narrative="on", experience_mode="all", cover_letter=False
    )
    assert build_resume._fit_assessment_will_be_consumed(args) is True


def test_fit_assessment_will_be_consumed_auto_experience_mode_returns_true() -> None:
    """experience-mode auto reads per_experience_scores even when
    fit-narrative is off."""
    args = argparse.Namespace(
        fit_narrative="off", experience_mode="auto", cover_letter=False
    )
    assert build_resume._fit_assessment_will_be_consumed(args) is True


def test_fit_assessment_will_be_consumed_auto_with_cover_letter_and_all_returns_false() -> (
    None
):
    """Auto-mode narrative defers to off when cover-letter is on; combined
    with experience-mode all, no consumer remains."""
    args = argparse.Namespace(
        fit_narrative="auto", experience_mode="all", cover_letter=True
    )
    assert build_resume._fit_assessment_will_be_consumed(args) is False


def test_fit_assessment_will_be_consumed_top_n_alone_returns_false() -> None:
    """top-N orders by recency, not fit_score, so it doesn't consume the
    assessment. With fit-narrative off, no consumer remains."""
    args = argparse.Namespace(
        fit_narrative="off", experience_mode="top-3", cover_letter=False
    )
    assert build_resume._fit_assessment_will_be_consumed(args) is False


def test_baseline_resume_for_fit_assessment_drops_out_of_window_experiences() -> None:
    """The fit_assessment baseline filter must drop experiences older than
    EXPERIENCE_DISPLAY_RECENCY_YEARS so the LLM doesn't score roles the
    reader will never see (PR #278 review)."""
    base = _resume_with_n_experiences(2)
    # exp-1 is "current" (start=2020, end=present); exp-2 is also "current".
    # Add one older role that should be dropped by the recency filter.
    older_exp = build_resume.Experience(
        id="exp-old",
        job_title="Junior Tester",
        company="OldCo",
        start_date="2000-01",
        end_date="2002-12",  # 23+ years ago, well outside the 15-year window
        general_role_description="Test platform engineering.",
        related_skills=("Python",),
        bullets=(
            build_resume.Bullet(
                id="b-old", text="Old bullet.", skills=(), impact_type="", domain=""
            ),
        ),
    )
    resume_with_old = dataclasses.replace(
        base, experiences=base.experiences + (older_exp,)
    )

    filtered = build_resume._baseline_resume_for_fit_assessment(resume_with_old)

    filtered_ids = {exp.id for exp in filtered.experiences}
    assert "exp-old" not in filtered_ids
    assert {"exp-1", "exp-2"} <= filtered_ids


def test_baseline_resume_for_fit_assessment_returns_input_when_all_in_window() -> None:
    """When every experience is in-window the helper returns the input
    unchanged (avoids needless dataclass copy)."""
    resume = _resume_with_n_experiences(3)
    filtered = build_resume._baseline_resume_for_fit_assessment(resume)
    assert filtered is resume


def test_apply_experience_compression_auto_no_assessment_compresses_lowest_ranked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """auto-mode without fit_assessment must fall back to compressing
    lowest-ranked experiences (last in display order) first, not first
    (which is the most relevant). PR #278 review."""
    resume = _resume_with_n_experiences(4)
    # Force overflow so compression actually fires.
    monkeypatch.setattr(
        "resume_builder.build_resume._compute_bullet_line_budget", lambda r: 1
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("auto"), resume, fit_assessment=None
    )
    compressed_ids = {
        exp.id for exp in result.experiences if exp.compression == "compressed"
    }
    # The 50% cap allows up to 2; lowest-ranked = highest indices.
    # exp-1 (most relevant) must NOT compress; exp-4 (lowest-ranked) must.
    assert "exp-1" not in compressed_ids
    assert "exp-4" in compressed_ids


def test_apply_experience_compression_top_n_floor_zero_is_noop() -> None:
    """1 experience -> 50% cap floors to 0 -> nothing compresses."""
    resume = _resume_with_n_experiences(1)
    result = build_resume.apply_experience_compression(
        _experience_mode_args("top-0"),  # bypasses CLI validator (programmatic)
        resume,
        fit_assessment=None,
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_auto_below_budget_no_op() -> None:
    """When the layout budget already accommodates every experience, auto
    mode does not compress anything (PR #278 / #271 spec)."""
    resume = _resume_with_n_experiences(2)  # small input, well under budget
    fit_assessment = build_resume.FitAssessment(
        overall_fit_score=30.0,
        overall_rationale="stretch",
        per_experience_scores=(
            build_resume.FitExperienceScore(
                experience_id="exp-1", fit_score=20.0, rationale="low"
            ),
            build_resume.FitExperienceScore(
                experience_id="exp-2", fit_score=80.0, rationale="high"
            ),
        ),
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("auto"), resume, fit_assessment=fit_assessment
    )
    assert all(exp.compression == "full" for exp in result.experiences)


def test_apply_experience_compression_auto_recomputes_budget_with_compressed_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-mode loop recomputes the budget on a simulated resume where
    compressed experiences have empty role descriptions, so the freed
    layout space credits back into the bullet budget (PR #278 review)."""
    captured: list[build_resume.ResumeIR] = []
    real_budget = build_resume._compute_bullet_line_budget

    def capture_then_real(r: build_resume.ResumeIR) -> int:
        captured.append(r)
        return real_budget(r)

    monkeypatch.setattr(
        "resume_builder.build_resume._compute_bullet_line_budget", capture_then_real
    )
    # Always over budget so the loop iterates and recomputes.
    monkeypatch.setattr(
        "resume_builder.build_resume._estimate_total_bullet_lines",
        lambda _bullets_lists: 9999,
    )

    resume = _resume_with_n_experiences(4)
    fit = build_resume.FitAssessment(
        overall_fit_score=30.0,
        overall_rationale="x",
        per_experience_scores=tuple(
            build_resume.FitExperienceScore(
                experience_id=f"exp-{i + 1}",
                fit_score=float(90 - i * 20),  # exp-1 high, exp-4 low
                rationale="",
            )
            for i in range(4)
        ),
    )
    build_resume.apply_experience_compression(
        _experience_mode_args("auto"), resume, fit_assessment=fit
    )

    # Initial overflow check (full resume) + at least one simulated recompute.
    assert len(captured) >= 2
    initial_resume = captured[0]
    assert all(exp.general_role_description for exp in initial_resume.experiences)
    # Subsequent calls feed simulated resumes with compressed exps' role
    # summaries cleared so the budget reflects the freed layout space.
    later_resumes = captured[1:]
    cleared_in_any_later = any(
        any(exp.general_role_description == "" for exp in r.experiences)
        for r in later_resumes
    )
    assert cleared_in_any_later


def test_apply_experience_compression_auto_compresses_lowest_fit_when_overflowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Force overflow by stubbing the budget below the simulated bullet line
    count; auto mode must then compress the lowest-fit-score experience first."""
    resume = _resume_with_n_experiences(4)
    fit_assessment = build_resume.FitAssessment(
        overall_fit_score=30.0,
        overall_rationale="stretch",
        per_experience_scores=(
            build_resume.FitExperienceScore(
                experience_id="exp-1", fit_score=90.0, rationale="strong"
            ),
            build_resume.FitExperienceScore(
                experience_id="exp-2", fit_score=10.0, rationale="weak"
            ),
            build_resume.FitExperienceScore(
                experience_id="exp-3", fit_score=70.0, rationale="ok"
            ),
            build_resume.FitExperienceScore(
                experience_id="exp-4", fit_score=20.0, rationale="weak2"
            ),
        ),
    )
    # Force the layout budget low enough to require some compression but not
    # so aggressive that it hits the 50% cap.
    monkeypatch.setattr(
        "resume_builder.build_resume._compute_bullet_line_budget", lambda r: 6
    )
    result = build_resume.apply_experience_compression(
        _experience_mode_args("auto"), resume, fit_assessment=fit_assessment
    )
    compressed_ids = {
        exp.id for exp in result.experiences if exp.compression == "compressed"
    }
    # Lowest-fit (exp-2 at 10) must be the first/only compressed entry.
    assert "exp-2" in compressed_ids
    # And the cap is respected — never more than 50%.
    assert len(compressed_ids) <= 2


def test_render_markdown_compressed_experience_omits_role_summary(
    tmp_path: Path,
) -> None:
    base = _resume_with_one_experience()
    compressed_exp = dataclasses.replace(base.experiences[0], compression="compressed")
    resume = dataclasses.replace(base, experiences=(compressed_exp,))
    output = tmp_path / "resume.md"
    build_resume.render_markdown(resume, output)
    content = output.read_text(encoding="utf-8")
    # Compressed entry: title + dates + the single highest-relevance bullet.
    assert "Senior SDET | ExampleCo" in content
    assert "2020-01 - present" in content
    assert "Built CI pipelines." in content
    # Role summary + related-skills lines must be suppressed for compressed.
    assert "Test platform engineering." not in content
    assert "Related skills:" not in content


def test_render_markdown_full_experience_keeps_role_summary(
    tmp_path: Path,
) -> None:
    """Sanity counterpart: when compression='full', the role summary stays."""
    base = _resume_with_one_experience()
    output = tmp_path / "resume.md"
    build_resume.render_markdown(base, output)
    content = output.read_text(encoding="utf-8")
    assert "Test platform engineering." in content
    assert "Related skills:" in content


def test_argparse_help_renders_without_format_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for #428: argparse formats help strings with the action's
    namespace dict, so unescaped `%` in any help string raises TypeError
    (e.g. `% o` in `50% of` parsed as the `%o` octal conversion). This guard
    runs `--help` end-to-end so any future `%`-in-help leak hard-fails in CI.
    """
    monkeypatch.setattr(sys, "argv", ["build_resume.py", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        build_resume.parse_args()
    # `--help` exits 0 after printing; a TypeError-on-format would propagate
    # as a different exception type before reaching this assertion.
    assert exc_info.value.code == 0
