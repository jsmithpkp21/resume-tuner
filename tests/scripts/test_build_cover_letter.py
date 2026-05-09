from __future__ import annotations

import argparse
import io
import json
import re
from collections.abc import Callable
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts import (
    build_cover_letter,
    cover_letter_export,
    document_export,
    jd_ingest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


SAMPLE_PROFILE_TOML = """\
[profile]
name = "Jane Doe"
headline = "Senior Staff Software Engineer, Test Automation"
location = "Austin, TX"
email = "jane@example.com"
phone = "(555) 555-1234"
website = ""
linkedin = "jane-doe"
github = ""
summary = "Senior Staff engineer with 18 years across hardware and CI."
"""

SAMPLE_EXPERIENCE_TOML = """\
[metadata]
schema_version = "1"
default_timezone = "UTC"

[[experience]]
id = "exp_acme_lead_2018"
job_title = "Lead Test Engineer"
company = "Acme Corp"
start_date = "2018-01"
end_date = "2026-01"
general_role_description = "Led automation efforts for a hardware platform team."
related_skills = ["Python", "Pytest", "CI Stability"]

[[experience.bullet_bank]]
id = "exp_acme_lead_2018_b01"
text = "Cut flaky-test rate by 30 percent across 18 hardware models."
skills = ["Python", "Pytest"]
impact_type = "reliability"
domain = "hardware"
"""

SAMPLE_JD_TEXT = """\
Senior Principal Test Framework Software Engineer

About Graphcore: We are building IPU accelerator hardware and software.
Hiring manager for this role: Alice Roberts.

Responsibilities:
- Lead test framework design across teams.
- Drive CI stability for our IPU stack.
"""


def _write_inputs(
    tmp_path: Path,
    *,
    profile_toml: str = SAMPLE_PROFILE_TOML,
    experience_toml: str = SAMPLE_EXPERIENCE_TOML,
    jd_text: str = SAMPLE_JD_TEXT,
) -> tuple[Path, Path, Path]:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(profile_toml, encoding="utf-8")
    experience_path = tmp_path / "experience_db.toml"
    experience_path.write_text(experience_toml, encoding="utf-8")
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(jd_text, encoding="utf-8")
    return profile_path, experience_path, jd_path


def _default_fit_assessment_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Neutral good-fit response for the shared fit_assessment call (#303).

    Issued to test handlers that don't supply a fit_assessment branch so
    cover-letter tests written before #303 keep working. Score 75 keeps
    the cover-letter body on the good-fit branch (no bridging addendum)
    so assertions about the existing prompt content remain valid.
    """
    experiences = payload.get("experiences") or []
    return {
        "overall_fit_score": 75,
        "overall_rationale": "default test response",
        "per_experience_scores": [
            {
                "experience_id": entry.get("experience_id", ""),
                "fit_score": 75,
                "rationale": "default test response",
            }
            for entry in experiences
            if isinstance(entry, dict) and entry.get("experience_id")
        ],
    }


def _patch_llm(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[str, dict[str, Any]], dict[str, Any]],
    *,
    counter: dict[str, int] | None = None,
) -> None:
    """Patch ``LLMClient.complete_json`` to dispatch on namespace.

    ``handler(namespace, user_payload)`` returns the dict the LLM would
    produce. ``counter`` is incremented per call when supplied. Pre-#303
    handlers raise ``AssertionError`` for unknown namespaces; when the
    unknown namespace is the shared ``fit_assessment`` call (added by
    #303) we transparently substitute a neutral good-fit response so
    pre-existing tests don't have to add a branch. Tests that want to
    assert stretch behavior should handle ``"fit_assessment"`` directly.
    """

    def fake(
        self: Any,
        *,
        namespace: str,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if counter is not None:
            counter[namespace] = counter.get(namespace, 0) + 1
        try:
            return handler(namespace, user_payload)
        except AssertionError:
            if namespace == "fit_assessment":
                return _default_fit_assessment_response(user_payload)
            raise

    monkeypatch.setattr(
        "scripts.build_cover_letter.LLMClient.complete_json", fake, raising=True
    )


def _enable_fixture_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESUME_BUILDER_LLM_FIXTURE", "1")
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)


def _good_body() -> dict[str, Any]:
    return {
        "opening": (
            "I am applying for the Senior Principal Test Framework Software Engineer "
            "role at Graphcore."
        ),
        "body_paragraphs": [
            "In 18 years at Acme Corp I cut flaky-test rate by 30 percent across "
            "18 hardware models, building deterministic CI patterns.",
            "I want to bring that focus on framework reliability to Graphcore's IPU stack.",
        ],
        "closing_paragraph": "I would welcome a conversation about how I can contribute.",
    }


def _run_cli(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> tuple[int, str]:
    monkeypatch.chdir(REPO_ROOT)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = build_cover_letter.main(argv)
    return rc, buf.getvalue()


def test_llm_disabled_hard_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile_path, experience_path, _ = _write_inputs(tmp_path)
    monkeypatch.delenv("RESUME_BUILDER_LLM_ENABLED", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_LLM_FIXTURE", raising=False)
    rc, _stdout = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    captured = capsys.readouterr()
    assert rc == build_cover_letter.EXIT_LLM_DISABLED
    assert "RESUME_BUILDER_LLM_ENABLED" in captured.err


def test_round_trip_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": "Alice Roberts", "confidence": 0.95}
        if namespace == build_cover_letter.BODY_NAMESPACE:
            return _good_body()
        raise AssertionError(f"unexpected namespace {namespace}")

    _patch_llm(monkeypatch, handler)

    out_dir = tmp_path / "out"
    rc, stdout = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--target-role",
            "Senior Principal Test Framework Software Engineer",
            "--output-dir",
            str(out_dir),
            "--outputs",
            "pdf,docx,md,html",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS, stdout
    summary = json.loads(stdout)
    assert summary["company"] == "Graphcore"
    assert summary["company_slug"] == "graphcore"
    pdf_path = out_dir / "graphcore_cover_letter.pdf"
    docx_path = out_dir / "graphcore_cover_letter.docx"
    md_path = out_dir / "graphcore_cover_letter.md"
    html_path = out_dir / "graphcore_cover_letter.html"
    for p in (pdf_path, docx_path, md_path, html_path):
        assert p.exists() and p.stat().st_size > 0, p

    md_text = md_path.read_text(encoding="utf-8")
    # JD short-circuited addressee inference (provided_text). Hiring manager
    # override was not supplied, so fallback applies.
    assert "Dear Hiring Team," in md_text
    assert "Graphcore" in md_text  # recipient block must contain the company
    assert "Sincerely," in md_text
    # Sender contact lines surface from the profile.
    assert "Austin, TX" in md_text
    assert "jane@example.com" in md_text


def test_outputs_default_writes_pdf_and_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default --outputs (pdf,docx) emits PDF + DOCX; not MD/HTML.

    Symmetric to the resume-side test
    ``test_outputs_default_writes_pdf_docx_and_ir`` and locks the canonical
    default decided in issue #230.
    """
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": "Alice Roberts", "confidence": 0.95}
        if namespace == build_cover_letter.BODY_NAMESPACE:
            return _good_body()
        raise AssertionError(f"unexpected namespace {namespace}")

    _patch_llm(monkeypatch, handler)

    out_dir = tmp_path / "out"
    rc, stdout = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--target-role",
            "Senior Principal Test Framework Software Engineer",
            "--output-dir",
            str(out_dir),
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS, stdout

    pdf_path = out_dir / "graphcore_cover_letter.pdf"
    docx_path = out_dir / "graphcore_cover_letter.docx"
    md_path = out_dir / "graphcore_cover_letter.md"
    html_path = out_dir / "graphcore_cover_letter.html"

    assert pdf_path.exists() and pdf_path.stat().st_size > 0, pdf_path
    assert docx_path.exists() and docx_path.stat().st_size > 0, docx_path
    assert not md_path.exists(), md_path
    assert not html_path.exists(), html_path


def test_job_text_file_short_circuits_addressee_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    counter: dict[str, int] = {}

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": "Alice Roberts", "confidence": 0.99}
        if namespace == build_cover_letter.BODY_NAMESPACE:
            return _good_body()
        raise AssertionError(namespace)

    _patch_llm(monkeypatch, handler, counter=counter)

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    # No addressee LLM call when JD is from a text file.
    assert build_cover_letter.ADDRESSEE_NAMESPACE not in counter
    assert counter.get(build_cover_letter.BODY_NAMESPACE) == 1


def test_hiring_manager_override_beats_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            # Should never be called when --hiring-manager is set.
            raise AssertionError("LLM addressee call should be skipped")
        return _good_body()

    _patch_llm(monkeypatch, handler)

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--hiring-manager",
            "Bob Smith",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    assert "Dear Bob Smith," in md_text


def test_company_override_beats_jd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    rc, stdout = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "OverrideCo",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    summary = json.loads(stdout)
    assert summary["company"] == "OverrideCo"
    assert summary["company_slug"] == "overrideco"
    md_text = (tmp_path / "out" / "overrideco_cover_letter.md").read_text("utf-8")
    assert "OverrideCo" in md_text


def test_confidence_threshold_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Low-confidence inferred name must fall back to Hiring Team.

    Use --job-url with a stub fetcher to exercise the LLM path; --job-text-file
    short-circuits the LLM addressee stage entirely.
    """

    profile_path, experience_path, _ = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    def fake_fetch(url: str) -> jd_ingest.FetchedPage:
        return jd_ingest.FetchedPage(
            status="ok",
            title="Hiring at Graphcore",
            description="Senior Principal Test Framework Engineer at Graphcore. Alice Roberts is a contact.",
            notes=(),
        )

    monkeypatch.setattr("scripts.jd_ingest._fetch_job_page_metadata", fake_fetch)

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": "Alice Roberts", "confidence": 0.5}
        return _good_body()

    _patch_llm(monkeypatch, handler)

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-url",
            "https://boards.greenhouse.io/graphcore/jobs/12345",
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    assert "Dear Hiring Team," in md_text


def test_substring_safety_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """High-confidence name not present in JD text must fall back."""

    profile_path, experience_path, _ = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    def fake_fetch(url: str) -> jd_ingest.FetchedPage:
        return jd_ingest.FetchedPage(
            status="ok",
            title="Hiring at Graphcore",
            description="Senior Principal role at Graphcore. No manager name listed.",
            notes=(),
        )

    monkeypatch.setattr("scripts.jd_ingest._fetch_job_page_metadata", fake_fetch)

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": "Carol Faker", "confidence": 0.99}
        return _good_body()

    _patch_llm(monkeypatch, handler)

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-url",
            "https://boards.greenhouse.io/graphcore/jobs/12345",
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    assert "Dear Hiring Team," in md_text
    assert "Carol Faker" not in md_text


def test_no_invented_numeric_metrics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS

    # Build numeric-token allowlist from inputs.
    profile_text = profile_path.read_text("utf-8")
    experience_text = experience_path.read_text("utf-8")
    jd_text = jd_path.read_text("utf-8")
    numeric_re = re.compile(r"\d[\d,.\-]*\d|\d")
    allowed = set(numeric_re.findall(profile_text + experience_text + jd_text))

    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    # Strip header date/contact lines (they're profile-derived). Body section
    # starts after the greeting.
    body = md_text.split("Dear Hiring Team,\n", 1)[1]
    # Drop the closing/signature.
    body = body.split("\nSincerely,\n", 1)[0]
    body_numbers = set(numeric_re.findall(body))
    invented = body_numbers - allowed
    assert not invented, (
        f"Body contains numeric tokens not present in inputs: {invented}"
    )


def test_no_ai_tells_in_body(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    forbidden = ["As an AI", "large language model", "I cannot", "I'm sorry"]
    for needle in forbidden:
        assert needle not in md_text, f"Forbidden phrase {needle!r} in output"


def test_renderer_is_isolated_from_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cover-letter DOCX must not contain section-header borders or
    list-bullet glyphs (which are resume-renderer artifacts)."""
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    out_dir = tmp_path / "out"
    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(out_dir),
            "--outputs",
            "docx",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS

    Document, _Pt, _Inches = document_export.require_python_docx()
    doc = Document(str(out_dir / "graphcore_cover_letter.docx"))
    # No paragraph should carry a bottom border (resume H2 marker).
    for p in doc.paragraphs:
        pPr = p._p.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pPr"
        )
        if pPr is None:
            continue
        pBdr = pPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pBdr"
        )
        assert pBdr is None, (
            f"Cover letter paragraph carried a border (resume artifact): {p.text!r}"
        )
        # No paragraph should use the List Bullet style.
        pStyle = pPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pStyle"
        )
        if pStyle is not None:
            val = pStyle.attrib.get(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val",
                "",
            )
            assert "List" not in val and "Bullet" not in val, (
                f"Cover letter paragraph used list/bullet style: {val!r}"
            )


def test_word_budget_overrun_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    long_paragraph = "scope and breadth " * 80
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            {
                "opening": "I am applying for the role at Graphcore.",
                "body_paragraphs": [long_paragraph],
                "closing_paragraph": "Thanks for your time.",
            }
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    rc, stdout = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
            "--word-budget",
            "50",
        ],
    )
    assert rc == build_cover_letter.EXIT_RENDERED_WITH_WARNINGS
    summary = json.loads(stdout)
    assert summary["warnings"]
    assert any("word count" in w.lower() for w in summary["warnings"])


def test_page_limit_strict_raises_on_overflow() -> None:
    from scripts.cover_letter_template import (
        CoverLetterBody,
        CoverLetterPreferences,
        compose_cover_letter,
    )

    class P:
        name = "Jane Doe"
        location = "Austin, TX"
        email = "jane@example.com"
        phone = "(555) 555-1234"
        website = ""
        linkedin = "jane-doe"
        github = ""

    huge = " ".join(["scope and breadth"] * 1500)
    ir = compose_cover_letter(
        profile=P(),
        addressee="Hiring Team",
        company_name="Acme",
        body=CoverLetterBody(
            opening="Opening.",
            body_paragraphs=(huge,),
            closing_paragraph="Closing.",
        ),
        preferences=CoverLetterPreferences(),
    )
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "x.pdf"
        # Default warn-only mode succeeds.
        cover_letter_export.render_pdf(ir, path, enforce_page_limit=False)
        assert path.exists()
        # Strict mode raises.
        with pytest.raises(cover_letter_export.CoverLetterPageLimitError):
            cover_letter_export.render_pdf(ir, path, enforce_page_limit=True)


def test_format_date_portable_day_format() -> None:
    from scripts.cover_letter_template import format_date

    assert format_date(date(2026, 1, 2)) == "January 2, 2026"


def test_no_cover_letter_table_uses_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Profile with no [cover_letter] table should render with defaults."""
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    md_text = (tmp_path / "out" / "graphcore_cover_letter.md").read_text("utf-8")
    assert "Sincerely,\n" in md_text  # default closing
    assert "Dear Hiring Team," in md_text  # default fallback


def test_output_byte_reproducibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Identical inputs + canned LLM = identical markdown body across runs."""
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)
    _patch_llm(
        monkeypatch,
        lambda namespace, payload: (
            _good_body()
            if namespace == build_cover_letter.BODY_NAMESPACE
            else {"hiring_manager_name": None, "confidence": 0.0}
        ),
    )

    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    base_argv = [
        "--profile",
        str(profile_path),
        "--experience-db",
        str(experience_path),
        "--job-text-file",
        str(jd_path),
        "--company",
        "Graphcore",
        "--outputs",
        "md",
    ]
    rc_a, _ = _run_cli(monkeypatch, base_argv + ["--output-dir", str(out_a)])
    rc_b, _ = _run_cli(monkeypatch, base_argv + ["--output-dir", str(out_b)])
    assert rc_a == rc_b == build_cover_letter.EXIT_SUCCESS
    md_a = (out_a / "graphcore_cover_letter.md").read_bytes()
    md_b = (out_b / "graphcore_cover_letter.md").read_bytes()
    assert md_a == md_b


def test_canonical_filename_kind_kwarg() -> None:
    assert (
        document_export.canonical_export_filename(
            "Graphcore", "pdf", kind="cover_letter"
        )
        == "graphcore_cover_letter.pdf"
    )
    assert (
        document_export.canonical_export_filename("Graphcore", "pdf")
        == "graphcore_resume.pdf"
    )


def test_cover_letter_module_invokes_run_pipeline_collecting_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scripts.cover_letter.generate_cover_letter delegates to the v1 pipeline.

    Replacement for the prior ``--with-cover-letter`` orchestrator tests
    after PR #223 was reconciled with main's ``--cover-letter`` surface
    (issue #229): the resume-orchestrated path now goes through
    ``scripts.cover_letter.generate_cover_letter`` -> ``scripts.build_cover_letter.run_pipeline_collecting_paths``.
    """
    if __package__ in {None, ""}:
        from scripts import cover_letter
    else:
        from scripts import cover_letter  # noqa: F401  -- kept for symmetry

    captured: dict[str, argparse.Namespace] = {}

    def fake_run(ns: argparse.Namespace) -> tuple[list[Path], list[str]]:
        captured["ns"] = ns
        return ([ns.output_dir / "graphcore_cover_letter.pdf"], [])

    monkeypatch.setattr(
        "scripts.build_cover_letter.run_pipeline_collecting_paths",
        fake_run,
        raising=True,
    )

    resume_args = argparse.Namespace(
        profile=tmp_path / "profile.toml",
        experience_db=tmp_path / "experience_db.toml",
        job_url="",
        job_text_file=tmp_path / "jd.txt",
        target_role="Senior Principal Test Framework Software Engineer",
        include_private_projects=False,
        verbose=False,
    )

    paths = cover_letter.generate_cover_letter(
        args=resume_args,
        output_dir=tmp_path / "cover_letters",
        company="Graphcore",
        role="Senior Principal Test Framework Software Engineer",
    )

    assert paths == [tmp_path / "cover_letters" / "graphcore_cover_letter.pdf"]
    ns = captured["ns"]
    assert ns.profile == resume_args.profile
    assert ns.experience_db == resume_args.experience_db
    assert ns.job_text_file == resume_args.job_text_file
    assert ns.company == "Graphcore"
    assert ns.target_role == "Senior Principal Test Framework Software Engineer"
    assert ns.output_dir == tmp_path / "cover_letters"
    assert ns.enforce_page_limit is False  # warn-only, never inherits resume's strict


def test_outputs_filter_propagates_to_cover_letter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """build_resume's --outputs reaches the cover-letter pipeline verbatim.

    Locks the issue #229 contract that the orchestrated cover letter
    honors the same --outputs filter as the resume — passing
    ('pdf',) here must not produce docx/md/html cover-letter files.
    """
    from scripts import cover_letter

    captured: dict[str, argparse.Namespace] = {}

    def fake_run(ns: argparse.Namespace) -> tuple[list[Path], list[str]]:
        captured["ns"] = ns
        return ([ns.output_dir / "graphcore_cover_letter.pdf"], [])

    monkeypatch.setattr(
        "scripts.build_cover_letter.run_pipeline_collecting_paths",
        fake_run,
        raising=True,
    )

    resume_args = argparse.Namespace(
        profile=tmp_path / "profile.toml",
        experience_db=tmp_path / "experience_db.toml",
        job_url="",
        job_text_file=tmp_path / "jd.txt",
        target_role="Senior Principal Test Framework Software Engineer",
        include_private_projects=False,
        verbose=False,
        outputs=("pdf",),
    )

    cover_letter.generate_cover_letter(
        args=resume_args,
        output_dir=tmp_path / "cover_letters",
        company="Graphcore",
        role="Senior Principal Test Framework Software Engineer",
    )

    assert captured["ns"].outputs == ("pdf",)


def test_outputs_empty_tuple_passes_through_not_defaulted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicitly empty `outputs` is forwarded as-is.

    The orchestrated path defaults only when the attribute is missing
    (`getattr` returns None), so programmatic callers that opt out of
    artifacts get the same behavior as the standalone CLI rather than
    silently rehydrating defaults.
    """
    from scripts import cover_letter

    captured: dict[str, argparse.Namespace] = {}

    def fake_run(ns: argparse.Namespace) -> tuple[list[Path], list[str]]:
        captured["ns"] = ns
        return ([], [])

    monkeypatch.setattr(
        "scripts.build_cover_letter.run_pipeline_collecting_paths",
        fake_run,
        raising=True,
    )

    resume_args = argparse.Namespace(
        profile=tmp_path / "profile.toml",
        experience_db=tmp_path / "experience_db.toml",
        job_url="",
        job_text_file=tmp_path / "jd.txt",
        target_role="",
        include_private_projects=False,
        verbose=False,
        outputs=(),
    )

    cover_letter.generate_cover_letter(
        args=resume_args,
        output_dir=tmp_path / "cover_letters",
        company="Graphcore",
        role="",
    )

    assert captured["ns"].outputs == ()


def test_outputs_str_input_raises_typeerror(tmp_path: Path) -> None:
    """A string `args.outputs` is rejected with a clear TypeError.

    Without this guard, `tuple("pdf")` would silently become
    ('p', 'd', 'f') and the downstream pipeline (which checks for
    `"pdf" in outputs`) would emit zero artifacts. Callers must parse
    comma-separated input upstream — same contract as the CLIs.
    """
    from scripts import cover_letter

    resume_args = argparse.Namespace(
        profile=tmp_path / "profile.toml",
        experience_db=tmp_path / "experience_db.toml",
        job_url="",
        job_text_file=tmp_path / "jd.txt",
        target_role="",
        include_private_projects=False,
        verbose=False,
        outputs="pdf",
    )

    with pytest.raises(TypeError, match="must be an iterable of tokens"):
        cover_letter.generate_cover_letter(
            args=resume_args,
            output_dir=tmp_path / "cover_letters",
            company="Graphcore",
            role="",
        )


def test_outputs_default_when_resume_omits_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the resume Namespace has no `outputs` attr, fall back to the
    cover-letter default (pdf, docx) so older callers still work."""
    from scripts import cover_letter

    captured: dict[str, argparse.Namespace] = {}

    def fake_run(ns: argparse.Namespace) -> tuple[list[Path], list[str]]:
        captured["ns"] = ns
        return ([], [])

    monkeypatch.setattr(
        "scripts.build_cover_letter.run_pipeline_collecting_paths",
        fake_run,
        raising=True,
    )

    resume_args = argparse.Namespace(
        profile=tmp_path / "profile.toml",
        experience_db=tmp_path / "experience_db.toml",
        job_url="",
        job_text_file=tmp_path / "jd.txt",
        target_role="",
        include_private_projects=False,
        verbose=False,
    )

    cover_letter.generate_cover_letter(
        args=resume_args,
        output_dir=tmp_path / "cover_letters",
        company="Graphcore",
        role="",
    )

    assert captured["ns"].outputs == build_cover_letter.DEFAULT_OUTPUTS


@pytest.mark.parametrize("bad_value", ["-0.1", "1.1", "2", "-1", "not-a-float"])
def test_addressee_confidence_threshold_rejects_invalid(
    bad_value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_cover_letter.parse_args(["--addressee-confidence-threshold", bad_value])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--addressee-confidence-threshold" in err


@pytest.mark.parametrize("good_value", ["0.0", "0.5", "1.0"])
def test_addressee_confidence_threshold_accepts_unit_interval(
    good_value: str,
) -> None:
    ns = build_cover_letter.parse_args(["--addressee-confidence-threshold", good_value])
    assert ns.addressee_confidence_threshold == float(good_value)


@pytest.mark.parametrize("bad_value", ["0", "-1", "-100", "not-an-int", "1.5"])
def test_word_budget_rejects_non_positive_int(
    bad_value: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        build_cover_letter.parse_args(["--word-budget", bad_value])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "--word-budget" in err


@pytest.mark.parametrize("good_value", ["1", "100", "350"])
def test_word_budget_accepts_positive_int(good_value: str) -> None:
    ns = build_cover_letter.parse_args(["--word-budget", good_value])
    assert ns.word_budget == int(good_value)


# ---------------------------------------------------------------------------
# Cover-letter bridging language for stretch fits (issue #303)
# ---------------------------------------------------------------------------


# Pad the sample JD past _MIN_JD_DESCRIPTION_CHARS (200) so
# _has_substantive_jd_context returns True and compute_fit_assessment
# actually fires under fixture mode.
_STRETCH_JD_TEXT = """\
Senior Backend Software Engineer at Western Union

We are building Java Spring Boot microservices and an Angular micro-frontend.
You will own production backend service development end to end: API design,
performance tuning, deployment, on-call rotation, incident response, and
the partner integrations that keep our payments rail running. We are a
backend-first team; test ownership lives elsewhere.

Responsibilities:
- Build and ship production Spring Boot services to handle payment flows.
- Drive API contract design with the integrations team.
- Participate in on-call rotation and incident response.
"""


def _patch_compute_fit_assessment(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, Any] | None
) -> None:
    """Force ``build_resume.compute_fit_assessment`` to return a fixed value.

    Bypasses the LLM call entirely so bridging-language tests don't depend
    on JD-content thresholds or the rubric prompt; we just want to assert
    how the cover-letter body draft reacts to a known assessment payload.
    """
    from scripts import build_resume as _br

    fake: Callable[[Any], _br.FitAssessment | None]
    if response is None:
        fake = lambda _resume: None  # noqa: E731
    else:
        fake_assessment = _br.FitAssessment(
            overall_fit_score=float(response["overall_fit_score"]),
            overall_rationale=response.get("overall_rationale", ""),
            per_experience_scores=tuple(
                _br.FitExperienceScore(
                    experience_id=entry["experience_id"],
                    fit_score=float(entry.get("fit_score", 0)),
                    rationale=entry.get("rationale", ""),
                )
                for entry in response.get("per_experience_scores", [])
            ),
        )
        fake = lambda _resume: fake_assessment  # noqa: E731

    # Patch the symbol re-exported into build_cover_letter so the cover-letter
    # pipeline picks up the fake without touching build_resume's own callers.
    monkeypatch.setattr(
        "scripts.build_cover_letter.compute_fit_assessment", fake, raising=True
    )


@pytest.mark.parametrize(
    "overall_fit_score,expects_bridging",
    [
        # Below the shared narrative gate (60) → stretch → bridging required.
        (35.0, True),
        # Above the gate → good fit → keep current enthusiastic-fit tone.
        (80.0, False),
    ],
)
def test_cover_letter_bridging_fires_only_for_stretch_fits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overall_fit_score: float,
    expects_bridging: bool,
) -> None:
    """Issue #303: the cover-letter body prompt must inject bridging
    instructions only when fit_assessment classifies the candidate-to-JD
    pairing as a stretch (overall_fit_score < _FIT_NARRATIVE_GATE_SCORE).
    Good-fit calls keep the existing prompt verbatim so the enthusiastic
    tone and cache key are unchanged.
    """
    profile_path, experience_path, _ = _write_inputs(tmp_path, jd_text=_STRETCH_JD_TEXT)
    jd_path = tmp_path / "jd.txt"
    jd_path.write_text(_STRETCH_JD_TEXT, encoding="utf-8")
    _enable_fixture_mode(monkeypatch)

    _patch_compute_fit_assessment(
        monkeypatch,
        {
            "overall_fit_score": overall_fit_score,
            "overall_rationale": "test-automation context applying to backend dev",
            "per_experience_scores": [
                {
                    "experience_id": "exp_acme_lead_2018",
                    "fit_score": overall_fit_score,
                    "rationale": "shared Java vocabulary, different daily context",
                },
            ],
        },
    )

    captured: dict[str, Any] = {}

    def handler(namespace: str, payload: dict[str, Any]) -> dict[str, Any]:
        if namespace == build_cover_letter.BODY_NAMESPACE:
            # The wrapper installed by _patch_llm passes the system prompt
            # via a separate argument; we capture the user_payload here and
            # rely on _capture_body_system_prompt for the prompt itself.
            captured["body_payload"] = payload
            return _good_body()
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": None, "confidence": 0.0}
        raise AssertionError(f"unexpected namespace {namespace}")

    body_prompts: list[str] = []

    def fake_complete_json(
        self: Any,
        *,
        namespace: str,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if namespace == build_cover_letter.BODY_NAMESPACE:
            body_prompts.append(system_prompt)
        return handler(namespace, user_payload)

    monkeypatch.setattr(
        "scripts.build_cover_letter.LLMClient.complete_json",
        fake_complete_json,
        raising=True,
    )

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Western Union",
            "--target-role",
            "Senior Backend Software Engineer",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS

    assert body_prompts, "cover-letter body LLM call did not fire"
    body_prompt = body_prompts[0]
    body_payload = captured["body_payload"]

    if expects_bridging:
        # Stretch-fit guidance must be present and reference bridging,
        # context, and the no-direct-experience guardrail.
        assert "STRETCH-FIT GUIDANCE" in body_prompt
        assert "While my background has been primarily in" in body_prompt
        assert "Do NOT claim direct experience" in body_prompt
        # fit_assessment_* keys are injected only on stretch so good-fit
        # cache keys stay untouched.
        assert body_payload["fit_assessment_overall_score"] == overall_fit_score
        assert body_payload["fit_assessment_rationale"]
    else:
        assert "STRETCH-FIT GUIDANCE" not in body_prompt
        assert "fit_assessment_overall_score" not in body_payload
        assert "fit_assessment_rationale" not in body_payload


def test_cover_letter_no_bridging_when_fit_assessment_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When compute_fit_assessment returns None (LLM disabled / thin JD /
    malformed response), the cover-letter body keeps the existing prompt
    unchanged — no bridging addendum, no fit_assessment_* payload keys.
    """
    profile_path, experience_path, jd_path = _write_inputs(tmp_path)
    _enable_fixture_mode(monkeypatch)

    _patch_compute_fit_assessment(monkeypatch, None)

    captured: dict[str, Any] = {}
    body_prompts: list[str] = []

    def fake_complete_json(
        self: Any,
        *,
        namespace: str,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if namespace == build_cover_letter.BODY_NAMESPACE:
            body_prompts.append(system_prompt)
            captured["body_payload"] = user_payload
            return _good_body()
        if namespace == build_cover_letter.ADDRESSEE_NAMESPACE:
            return {"hiring_manager_name": None, "confidence": 0.0}
        raise AssertionError(f"unexpected namespace {namespace}")

    monkeypatch.setattr(
        "scripts.build_cover_letter.LLMClient.complete_json",
        fake_complete_json,
        raising=True,
    )

    rc, _ = _run_cli(
        monkeypatch,
        [
            "--profile",
            str(profile_path),
            "--experience-db",
            str(experience_path),
            "--job-text-file",
            str(jd_path),
            "--company",
            "Graphcore",
            "--output-dir",
            str(tmp_path / "out"),
            "--outputs",
            "md",
        ],
    )
    assert rc == build_cover_letter.EXIT_SUCCESS
    assert body_prompts
    assert "STRETCH-FIT GUIDANCE" not in body_prompts[0]
    assert "fit_assessment_overall_score" not in captured["body_payload"]
    assert "fit_assessment_rationale" not in captured["body_payload"]


def test_build_body_system_prompt_returns_base_for_good_fit() -> None:
    """Unit-level: the prompt builder is unchanged for good fits."""
    base = build_cover_letter._build_body_system_prompt(stretch=False)
    assert "STRETCH-FIT GUIDANCE" not in base
    assert "HARD RULES" in base


def test_build_body_system_prompt_appends_addendum_for_stretch() -> None:
    """Unit-level: the prompt builder appends the bridging addendum for
    stretch fits and keeps the existing HARD RULES block intact so the
    LLM still sees both layers of guidance."""
    augmented = build_cover_letter._build_body_system_prompt(stretch=True)
    assert "HARD RULES" in augmented
    assert "STRETCH-FIT GUIDANCE" in augmented
    assert "Acknowledge the transition explicitly" in augmented
    assert "Do NOT claim direct experience" in augmented
