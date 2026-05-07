from __future__ import annotations

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

from scripts import build_resume, jd_ingest
from scripts.build_resume import (
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
from scripts.jd_ingest import FetchedPage, ingest_job_context
from scripts.measure_skills_lines import (
    TARGET_LINES_MAX,
    TARGET_LINES_MIN,
    load_font_pair,
    measure_skills_section,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_resume.py"
PROFILE = REPO_ROOT / "data" / "profile" / "profile.toml"
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


def test_load_profile_applies_local_override_for_personal_fields(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Baseline Name"
headline = "Engineer"
location = "Austin"
email = "baseline@example.com"
phone = "111"
website = ""
linkedin = "baseline-linkedin"
github = "baseline-github"
summary = "tracked summary"

[[education]]
degree = "Baseline Degree"

[[leadership_community]]
title = "Baseline Leadership"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    local_path = tmp_path / "profile.local.toml"
    local_path.write_text(
        """
[profile]
name = "Local Name"
headline = "Senior Staff Software Engineer"
email = "local@example.com"
phone = "222"
linkedin = "local-linkedin"
github = "local-github"
summary = "should not override"

[[education]]
degree = "Local Degree"

[[leadership_community]]
title = "Local Leadership"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    assert profile.name == "Local Name"
    assert profile.headline == "Senior Staff Software Engineer"
    assert profile.email == "local@example.com"
    assert profile.phone == "222"
    assert profile.linkedin == "local-linkedin"
    assert profile.github == "local-github"
    # Keep non-personal copy in tracked baseline profile.
    assert profile.summary == "tracked summary"
    # Optional local sections replace tracked sections when present.
    assert profile.education_entries[0].degree == "Local Degree"
    assert profile.leadership_community_entries[0].title == "Local Leadership"


def test_load_profile_rejects_non_file_local_override(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Baseline Name"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = "tracked summary"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "profile.local.toml").mkdir()

    with pytest.raises(ValueError, match="regular file"):
        load_profile(profile_path)


def test_load_profile_local_override_error_mentions_derived_filename(
    tmp_path: Path,
) -> None:
    profile_path = tmp_path / "candidate-profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Baseline Name"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = "tracked summary"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "candidate-profile.local.toml").mkdir()

    with pytest.raises(ValueError, match="candidate-profile.local.toml"):
        load_profile(profile_path)


def test_load_profile_rejects_local_override_as_base_path(tmp_path: Path) -> None:
    local_profile_path = tmp_path / "profile.local.toml"
    local_profile_path.write_text(
        """
[profile]
name = "Local Name"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = ""
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="already a local override file"):
        load_profile(local_profile_path)


def test_load_profile_rejects_non_table_local_section_entry(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Baseline Name"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = ""
github = ""
summary = "tracked summary"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    local_path = tmp_path / "profile.local.toml"
    local_path.write_text(
        """
education = ["invalid-entry"]

[profile]
name = "Local Name"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError, match="profile.local.toml education entries must be tables"
    ):
        load_profile(profile_path)


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
    assert "Architect, Python Test Framework (Video)" in html_text
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

    monkeypatch.setattr("scripts.jd_ingest.socket.getaddrinfo", fake_getaddrinfo)
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
    from scripts.jd_ingest import _infer_source

    assert _infer_source("linkedin.com.evil.com") == "company-site"


def test_infer_source_accepts_linkedin_subdomain() -> None:
    from scripts.jd_ingest import _infer_source

    assert _infer_source("www.linkedin.com") == "linkedin"


def test_normalize_linkedin_slug_rejects_company_url() -> None:
    from scripts.build_resume import _normalize_linkedin_slug

    assert _normalize_linkedin_slug("https://www.linkedin.com/company/foo") == ""


def test_normalize_linkedin_slug_accepts_in_url() -> None:
    from scripts.build_resume import _normalize_linkedin_slug

    assert (
        _normalize_linkedin_slug(
            "https://www.linkedin.com/in/jonathan-j-smith-automation"
        )
        == "jonathan-j-smith-automation"
    )


def test_normalize_github_username_rejects_gist_host() -> None:
    from scripts.build_resume import _normalize_github_username

    assert _normalize_github_username("https://gist.github.com/user") == ""


def test_normalize_github_username_accepts_github_com() -> None:
    from scripts.build_resume import _normalize_github_username

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

    monkeypatch.setattr("scripts.build_resume._score_bullet_relevance", fake_scores)

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
    caplog.set_level(logging.DEBUG, logger="scripts.build_resume")

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

    monkeypatch.setattr("scripts.build_resume._score_bullet_relevance", fake_scores)

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

    monkeypatch.setattr("scripts.build_resume._score_bullet_relevance", raise_on_score)
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

    monkeypatch.setattr("scripts.build_resume._score_bullet_relevance", empty_scores)

    trimmed = trim_for_role(resume)
    assert trimmed.experiences[0] == resume.experiences[0]


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
        "scripts.build_resume._enrich_experience_bullets", fake_enrichment
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
        "scripts.build_resume._enrich_experience_bullets", raise_on_enrich
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
    non-determinism from profile.local overrides on contributor machines.
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
    monkeypatch.setattr("scripts.build_resume.PROFILE_SUMMARY_MAX_WORDS", max_words)
    monkeypatch.setattr(
        "scripts.build_resume.PROFILE_SUMMARY_MIN_RATIO", PROFILE_SUMMARY_MIN_RATIO
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
    monkeypatch.setattr("scripts.build_resume.PROFILE_SUMMARY_MAX_WORDS", max_words)

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
    # (e.g. a profile.local.toml override can vary the opening fragment length).
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
    monkeypatch.setattr("scripts.build_resume.PROFILE_SUMMARY_MAX_WORDS", 10)
    monkeypatch.setattr("scripts.build_resume.PROFILE_SUMMARY_MIN_RATIO", 1.5)

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

    monkeypatch.setattr("scripts.build_resume.LLMClient.from_env", fail_if_called)

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
        "scripts.build_resume.LLMClient.from_env",
        lambda *_args, **_kwargs: object(),
    )

    first_bullet_id = resume.experiences[0].bullets[0].id

    def fake_enrich(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume, experience
        return {first_bullet_id: {"confidence": 0.88, "tags": ["sdet"]}}

    monkeypatch.setattr("scripts.build_resume._enrich_experience_bullets", fake_enrich)

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
        "scripts.build_resume.LLMClient.from_env",
        lambda *_args, **_kwargs: object(),
    )

    first_bullet_id = resume.experiences[0].bullets[0].id

    def fake_enrich(
        *, client: Any, resume: Any, experience: Any
    ) -> dict[str, dict[str, object]]:
        del client, resume, experience
        return {first_bullet_id: {"confidence": 0.77, "tags": ["sdet"]}}

    monkeypatch.setattr("scripts.build_resume._enrich_experience_bullets", fake_enrich)

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
        "scripts.build_resume._rewrite_experience_bullets", fake_rewrite
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
        "scripts.build_resume._rewrite_experience_bullets", fake_rewrite
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
        "scripts.build_resume._rewrite_experience_bullets", fake_rewrite_empty
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
        "scripts.build_resume._rewrite_experience_bullets", raise_on_rewrite
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
        "scripts.build_resume._rewrite_experience_bullets", fake_rewrite
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
        "scripts.build_resume._rewrite_experience_bullets", fake_rewrite
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


def test_build_resume_cli_cover_letter_flag_emits_stub(tmp_path: Path) -> None:
    """--cover-letter writes a placeholder markdown file under cover_letters/."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _run_build_resume_cli(
        experience_db=REPO_ROOT / "data" / "experience" / "experience_db.toml",
        profile_path=profile_path,
        output_dir=output_dir,
        extra_args=("--cover-letter",),
    )
    assert result.returncode == 0, result.stderr

    cover_letter_dir = output_dir / "cover_letters"
    expected_path = cover_letter_dir / "company_cover_letter.md"
    assert expected_path.exists()
    body = expected_path.read_text(encoding="utf-8")
    assert "placeholder" in body.lower()
    assert "issue #229" in body
    assert "placeholder" in result.stdout.lower()


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


def test_outputs_default_writes_only_pdf_and_ir(tmp_path: Path) -> None:
    """Default --outputs=pdf produces PDF + IR snapshots; no HTML/MD/DOCX."""
    output_dir = tmp_path / "out"
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(PROFILE.read_text(encoding="utf-8"), encoding="utf-8")

    result = _outputs_cli(output_dir=output_dir, profile_path=profile_path)
    assert result.returncode == 0, result.stderr

    assert (output_dir / "resumes" / "company_resume.pdf").exists()
    assert (
        output_dir / "resumes" / "latest_resume_processed_ir_snapshot.json"
    ).exists()
    assert (output_dir / "resumes" / "latest_resume_processed_ir_snapshot.txt").exists()

    # HTML, MD, DOCX absent under default --outputs=pdf.
    assert not (output_dir / "resumes" / "latest_resume_processed.html").exists()
    assert not (
        output_dir / "resumes" / "latest_default_resume_processed.html"
    ).exists()
    assert not (output_dir / "resumes" / "latest_resume_processed.md").exists()
    assert not (output_dir / "resumes" / "company_resume.docx").exists()


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
    from scripts.build_resume import _extract_company_via_llm
    from scripts.jd_ingest import JobContext

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

    from scripts.jd_ingest import _extract_company_name, _infer_source

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

    from scripts.jd_ingest import _extract_company_name, _infer_source

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

    from scripts.jd_ingest import _extract_company_name, _infer_source

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
