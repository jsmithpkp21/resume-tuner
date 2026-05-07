from __future__ import annotations

from pathlib import Path

import pytest

from scripts import build_resume
from scripts.build_resume import assemble_baseline_resume, load_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
# data/profile/profile.toml is per-contributor runtime input (gitignored).
# Tests use a tracked synthetic baseline so behavior is reproducible across machines and CI.
PROFILE = REPO_ROOT / "tests" / "fixtures" / "profile" / "profile_baseline.toml"


def test_expand_profile_summary_to_min_words_uses_readable_title_segment_for_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = load_profile(PROFILE)
    resume = assemble_baseline_resume(
        profile=profile,
        target_role="",
        target_company="",
        job_context=None,
        experiences=(),
        skills_by_category={},
    )
    monkeypatch.setattr(
        build_resume,
        "derive_resume_title",
        lambda _resume: "Software Engineer / Platform",
    )

    result = build_resume._expand_profile_summary_to_min_words(
        "Engineer with strengths in automation.",
        resume,
        min_words=12,
        fragments=[],
    )

    assert "Focus includes Software Engineer delivery." in result
