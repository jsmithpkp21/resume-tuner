from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_resume import load_profile
from scripts.jd_ingest import FetchedPage, ingest_job_context

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_resume.py"
PROFILE = REPO_ROOT / "data" / "profile" / "profile.toml"
LINKEDIN_JOB_URL = (
    "https://www.linkedin.com/jobs/search-results/?"
    "currentJobId=4380299765&keywords=SDET&origin=JOBS_HOME_SEARCH_BUTTON"
)
SCHWAB_JOB_URL = (
    "https://www.schwabjobs.com/job/austin/"
    "sr-sdet-workplace-services-engineering/33727/92422911552"
)


def test_load_profile_reads_profile_table() -> None:
    profile = load_profile(PROFILE)
    assert profile.name
    assert profile.summary
    assert profile.education_entries
    assert profile.leadership_community_entries
    assert profile.linkedin == "jonathan-j-smith-automation"
    assert profile.github == "jsmithpkp21"


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


def test_build_resume_cli_generates_baseline_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "baseline"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
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

    html_path = output_dir / "resume_baseline.html"
    md_path = output_dir / "resume_baseline.md"
    snapshot_path = output_dir / "resume_ir_snapshot.json"

    assert html_path.exists()
    assert md_path.exists()
    assert snapshot_path.exists()

    html_text = html_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert "Jonathan Smith" in html_text
    assert '<p class="headline">Staff Software Engineer</p>' in html_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in html_text
    assert "github.com/jsmithpkp21" in html_text
    assert "Architect, Python Test Framework (Video)" in html_text
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in md_text
    assert "github.com/jsmithpkp21" in md_text
    assert snapshot["profile"]["linkedin"] == "jonathan-j-smith-automation"
    assert (
        snapshot["profile"]["linkedin_url"]
        == "linkedin.com/in/jonathan-j-smith-automation"
    )
    assert snapshot["profile"]["github"] == "jsmithpkp21"
    assert snapshot["profile"]["github_url"] == "github.com/jsmithpkp21"


def test_build_resume_cli_accepts_job_url_and_generates_job_context(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "from_job_url"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
            "--job-url",
            LINKEDIN_JOB_URL,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    html_text = (output_dir / "resume_baseline.html").read_text(encoding="utf-8")
    snapshot = json.loads(
        (output_dir / "resume_ir_snapshot.json").read_text(encoding="utf-8")
    )

    assert '<p class="headline">SDET</p>' in html_text
    assert "Target role: SDET" in html_text
    assert snapshot["target_role"] == "SDET"
    assert snapshot["job_context"]["source"] == "linkedin"
    assert snapshot["job_context"]["job_id"] == "4380299765"
    assert snapshot["job_context"]["input_url"] == LINKEDIN_JOB_URL


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
        (output_dir / "resume_ir_snapshot.json").read_text(encoding="utf-8")
    )

    assert snapshot["target_role"] == "Senior SDET"
    assert snapshot["target_company"] == "Charles Schwab"
    assert snapshot["job_context"]["source"] == "job-text-file"
    assert snapshot["job_context"]["fetch_status"] == "provided_text"


def test_build_resume_cli_rejects_typo_hjob_text_file_flag(tmp_path: Path) -> None:
    output_dir = tmp_path / "invalid_flag"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
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
