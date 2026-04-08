from __future__ import annotations

import io
import json
import logging
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
    Bullet,
    Experience,
    assemble_baseline_resume,
    enrich_data,
    load_experiences,
    load_profile,
    transform_for_role,
    trim_by_rules,
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
    assert ".skills-category { margin: 0; }" in html_text
    assert '<p class="skills-category"><strong>' in html_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in html_text
    assert "github.com/jsmithpkp21" in html_text
    assert "Architect, Python Test Framework (Video)" in html_text
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert html_text.index("<h2>Summary</h2>") < html_text.index("<h2>Skills</h2>")
    assert html_text.index("<h2>Skills</h2>") < html_text.index("<h2>Experience</h2>")
    assert " • " in html_text
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
    assert md_text.index("## Summary") < md_text.index("## Skills")
    assert md_text.index("## Skills") < md_text.index("## Experience")
    assert " • " in md_text
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
    assert " • " in text_snapshot


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


def test_trim_by_rules_enforces_total_bullet_cap() -> None:
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

    assert sum(len(experience.bullets) for experience in trimmed.experiences) == 20
    assert all(len(experience.bullets) >= 3 for experience in trimmed.experiences)
    assert len(trimmed.experiences[0].bullets) == 3


# ---------------------------------------------------------------------------
# transform_for_role tests
# ---------------------------------------------------------------------------


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
        "Transformed inherited ADB/UI Automator test flow into a lightweight "
        "abstraction layer for Android-based embedded UI testing across PolyOS, "
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
