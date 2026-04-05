from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from http.client import HTTPMessage
from pathlib import Path
from typing import Any
from urllib.request import Request

import pytest

from scripts import jd_ingest
from scripts.build_resume import (
    assemble_baseline_resume,
    load_experiences,
    load_profile,
    trim_for_role,
)
from scripts.jd_ingest import FetchedPage, ingest_job_context

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_resume.py"
PROFILE = REPO_ROOT / "data" / "profile" / "profile.toml"
SCHWAB_JOB_URL = (
    "https://www.schwabjobs.com/job/austin/"
    "sr-sdet-workplace-services-engineering/33727/92422911552"
)
SCHWAB_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "job_pages" / "schwab_sr_sdet.html"


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
    text_snapshot_path = output_dir / "resume_ir_snapshot.txt"

    assert html_path.exists()
    assert md_path.exists()
    assert snapshot_path.exists()
    assert text_snapshot_path.exists()

    html_text = html_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    text_snapshot = text_snapshot_path.read_text(encoding="utf-8")

    assert "Jonathan Smith" in html_text
    assert '<p class="headline">Staff Software Engineer</p>' in html_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in html_text
    assert "github.com/jsmithpkp21" in html_text
    assert "Architect, Python Test Framework (Video)" in html_text
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert html_text.index("<h2>Summary</h2>") < html_text.index("<h2>Skills</h2>")
    assert html_text.index("<h2>Skills</h2>") < html_text.index("<h2>Experience</h2>")
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
    assert md_text.index("## Summary") < md_text.index("## Skills")
    assert md_text.index("## Skills") < md_text.index("## Experience")
    assert "linkedin.com/in/jonathan-j-smith-automation" in md_text
    assert "github.com/jsmithpkp21" in md_text
    assert snapshot["profile"]["linkedin"] == "jonathan-j-smith-automation"
    assert (
        snapshot["profile"]["linkedin_url"]
        == "linkedin.com/in/jonathan-j-smith-automation"
    )
    assert snapshot["profile"]["github"] == "jsmithpkp21"
    assert snapshot["profile"]["github_url"] == "github.com/jsmithpkp21"
    assert "summary:" in text_snapshot
    assert "skills:" in text_snapshot
    assert "experience:" in text_snapshot
    assert "education:" in text_snapshot
    assert "leadership_community:" in text_snapshot
    assert "job_context:" in text_snapshot
    assert (
        "profile.linkedin_url: linkedin.com/in/jonathan-j-smith-automation"
        in text_snapshot
    )
    assert "profile.github_url: github.com/jsmithpkp21" in text_snapshot
    assert text_snapshot.index("summary:") < text_snapshot.index("skills:")
    assert text_snapshot.index("skills:") < text_snapshot.index("experience:")


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

    html_text = (output_dir / "resume_baseline.html").read_text(encoding="utf-8")
    snapshot = json.loads(
        (output_dir / "resume_ir_snapshot.json").read_text(encoding="utf-8")
    )

    assert '<p class="headline">Sr. SDET</p>' in html_text
    assert "Target role: Sr. SDET" in html_text
    assert snapshot["target_role"] == "Sr. SDET"
    assert snapshot["target_company"] == "Charles Schwab"
    assert snapshot["job_context"]["source"] == "company-site"
    assert snapshot["job_context"]["job_id"] == "92422911552"
    assert snapshot["job_context"]["input_url"] == SCHWAB_JOB_URL
    assert snapshot["job_context"]["fetch_status"] == "fetched"


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


def test_ingest_job_context_rejects_unsupported_url_scheme() -> None:
    with pytest.raises(ValueError, match="http or https"):
        ingest_job_context("file:///tmp/job.html")


def test_ingest_job_context_rejects_localhost_target() -> None:
    with pytest.raises(ValueError, match="localhost"):
        ingest_job_context("http://localhost/jobs/123")


def test_ingest_job_context_rejects_private_ip_target() -> None:
    with pytest.raises(ValueError, match="non-public IP"):
        ingest_job_context("https://10.0.0.5/jobs/123")


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


def test_fetch_job_page_metadata_limits_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)

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
        [sys.executable, str(SCRIPT), "--output-dir", str(tmp_path), "--job-url", url],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    import json as _json

    snapshot = _json.loads(
        (tmp_path / "resume_ir_snapshot.json").read_text(encoding="utf-8")
    )
    assert snapshot["job_context"]["source"] == "linkedin"
    assert snapshot["job_context"]["role_hint"] == "SDET"


def test_trim_for_role_keeps_subset_and_reorders_by_score(
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
    assert len(first_before.bullets) == 5
    assert len(first_after.bullets) == 4

    assert [bullet.id for bullet in first_after.bullets] == [
        first_before.bullets[1].id,
        first_before.bullets[3].id,
        first_before.bullets[4].id,
        first_before.bullets[2].id,
    ]
    assert {bullet.id for bullet in first_after.bullets}.issubset(
        {bullet.id for bullet in first_before.bullets}
    )


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
