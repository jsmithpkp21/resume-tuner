"""Tests for skills layout packing (Issue #42)."""

from __future__ import annotations

import builtins
import logging
from dataclasses import dataclass

import pytest

from scripts import select_skills as select_skills_module
from scripts.select_skills import (
    MIN_SKILLS_PER_CATEGORY,
    TARGET_CATEGORY_MAX,
    TARGET_LINES_MAX,
    TARGET_LINES_MIN,
    TOP_N_SKILLS,
    _compute_category_industry_weights,
    _compute_skill_scores,
    _expand_jd_forms,
    _normalize_skill_near_dupe_key,
    _section_layout,
    _skill_role_relevance,
    _tokenize_role_text,
    _wrap_widths,
    cap_skills_by_score,
    estimate_line_count,
    join_skills,
    normalize_skill_near_dupes,
    pack_skills_to_budget,
    prioritize_skills_by_importance,
    select_skills,
)


def test_estimate_line_count_handles_empty_and_non_empty() -> None:
    assert estimate_line_count("Testing", [], font_regular=None, font_bold=None) == 0
    assert (
        estimate_line_count(
            "Testing",
            ["Automation", "Regression", "API", "CI/CD"],
            font_regular=None,
            font_bold=None,
        )
        >= 1
    )


def test_pack_skills_to_budget_hits_target_range_for_large_input() -> None:
    source = {
        "Automation & Frameworks": [f"framework_{idx}" for idx in range(1, 30)],
        "Architecture": [f"arch_{idx}" for idx in range(1, 25)],
        "Quality Engineering": [f"qe_{idx}" for idx in range(1, 30)],
        "Leadership": [f"lead_{idx}" for idx in range(1, 22)],
    }
    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    total_lines, _ = _section_layout(packed, font_regular=None, font_bold=None)
    assert TARGET_LINES_MIN <= total_lines <= TARGET_LINES_MAX


def test_pack_skills_to_budget_preserves_minimum_skills_per_category() -> None:
    source = {
        "A": [f"a_{idx}" for idx in range(25)],
        "B": [f"b_{idx}" for idx in range(25)],
        "C": [f"c_{idx}" for idx in range(25)],
    }
    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    assert set(packed) == set(source)
    for skills in packed.values():
        assert len(skills) >= MIN_SKILLS_PER_CATEGORY


def test_pack_skills_to_budget_is_deterministic_and_does_not_mutate_input() -> None:
    source = {
        "Python": ["pytest", "asyncio", "typing", "packaging", "toml"],
        "Testing": ["contract testing", "integration testing", "linting"],
    }
    baseline = {key: list(value) for key, value in source.items()}
    packed1 = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    packed2 = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    assert source == baseline
    assert packed1 == packed2


def test_pack_skills_to_budget_can_drop_singleton_categories_when_over_budget() -> None:
    source = {f"Category {idx:02d}": [f"skill_{idx:02d}"] for idx in range(1, 16)}
    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    total_lines, _ = _section_layout(packed, font_regular=None, font_bold=None)

    assert total_lines <= TARGET_LINES_MAX
    assert len(packed) < len(source)


def test_pack_skills_to_budget_progresses_when_single_trims_do_not_immediately_unwrap() -> (
    None
):
    source = {
        "Automation & Frameworks": [f"framework_{idx}" for idx in range(1, 30)],
        "Architecture": [f"arch_{idx}" for idx in range(1, 25)],
        "Quality Engineering": [f"qe_{idx}" for idx in range(1, 30)],
        "Leadership": [f"lead_{idx}" for idx in range(1, 22)],
    }

    baseline_lines, _ = _section_layout(source, font_regular=None, font_bold=None)
    assert baseline_lines > TARGET_LINES_MAX

    # Regression precondition: one-skill trim candidates do not immediately change
    # wrapped line count, which previously caused the optimizer to stall.
    single_trim_lines: set[int] = set()
    for category, skills in source.items():
        candidate = {cat: list(values) for cat, values in source.items()}
        candidate[category] = skills[:-1]
        candidate_lines, _ = _section_layout(
            candidate, font_regular=None, font_bold=None
        )
        single_trim_lines.add(candidate_lines)

    assert single_trim_lines == {baseline_lines}

    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    packed_lines, _ = _section_layout(packed, font_regular=None, font_bold=None)

    assert packed_lines <= TARGET_LINES_MAX
    assert any(len(source[cat]) - len(packed[cat]) >= 2 for cat in source)


def test_pack_skills_to_budget_reduces_category_count_even_when_lines_already_fit() -> (
    None
):
    source = {f"Category {idx:02d}": [f"skill_{idx:02d}"] for idx in range(1, 13)}

    baseline_lines, _ = _section_layout(source, font_regular=None, font_bold=None)
    assert TARGET_LINES_MIN <= baseline_lines <= TARGET_LINES_MAX
    assert len(source) > TARGET_CATEGORY_MAX

    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    packed_lines, _ = _section_layout(packed, font_regular=None, font_bold=None)

    assert packed_lines <= TARGET_LINES_MAX
    assert len(packed) <= TARGET_CATEGORY_MAX
    assert sum(len(skills) for skills in packed.values()) == sum(
        len(skills) for skills in source.values()
    )


def test_pack_skills_to_budget_reduces_categories_under_category_only_pressure() -> (
    None
):
    source = {
        f"Category {idx:02d}": [f"skill_{idx}_{skill_idx}" for skill_idx in range(1, 5)]
        for idx in range(1, 13)
    }

    baseline_lines, _ = _section_layout(source, font_regular=None, font_bold=None)
    assert TARGET_LINES_MIN <= baseline_lines <= TARGET_LINES_MAX
    assert len(source) > TARGET_CATEGORY_MAX

    packed = pack_skills_to_budget(source, font_regular=None, font_bold=None)
    packed_lines, _ = _section_layout(packed, font_regular=None, font_bold=None)

    assert packed_lines <= TARGET_LINES_MAX
    assert len(packed) <= TARGET_CATEGORY_MAX


def test_pack_skills_to_budget_keeps_programming_category_when_protected() -> None:
    source = {
        "Programming & Scripting": [
            "Python",
            "Java",
            "Very Long Legacy Scripting Capability",
            "Legacy Build Language",
        ],
        "A": ["a1", "a2", "a3"],
        "B": ["b1", "b2", "b3"],
    }
    skill_scores = {"Python": 9.0, "Java": 8.0}

    packed = pack_skills_to_budget(
        source,
        font_regular=None,
        font_bold=None,
        target_min=0,
        target_max=50,
        target_category_max=2,
        skill_scores=skill_scores,
    )

    assert "Programming & Scripting" in packed
    assert "Python" in packed["Programming & Scripting"]
    assert "Java" in packed["Programming & Scripting"]


def test_pack_skills_to_budget_moves_protected_skills_to_front_on_merge() -> None:
    source = {
        "Programming & Scripting": ["Python", "Java", "C"],
        "CI/CD & Tooling": ["Git", "Jenkins"],
    }

    packed = pack_skills_to_budget(
        source,
        font_regular=None,
        font_bold=None,
        target_min=0,
        target_max=50,
        target_category_max=1,
        skill_scores={"Python": 9.0, "Java": 8.0},
    )

    assert len(packed) == 1
    merged_skills = next(iter(packed.values()))
    assert merged_skills[:2] == ["Python", "Java"]


def test_join_skills_uses_shared_separator() -> None:
    assert join_skills(["Python", "Pytest", "CI/CD"]) == "Python • Pytest • CI/CD"


def test_wrap_widths_does_not_count_leading_space_on_wrapped_lines() -> None:
    wrapped = _wrap_widths(
        token_widths=[4.0, 4.0],
        line_limit=8.0,
        prefix_width=4.0,
        inter_token_space=1.0,
    )
    assert wrapped == [8.0, 4.0]


def test_load_measure_backend_falls_back_on_import_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    original_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "measure_skills_lines":
            raise ImportError("simulated Pillow import failure")
        if name == "scripts" and "measure_skills_lines" in fromlist:
            raise ImportError("simulated Pillow import failure")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(select_skills_module, "_MEASURE_BACKEND", False)
    monkeypatch.setattr(builtins, "__import__", fake_import)

    with caplog.at_level(logging.WARNING):
        backend = select_skills_module._load_measure_backend()

    assert backend is None
    assert "skills packing fallback estimator enabled" in caplog.text


@dataclass(frozen=True)
class _DummyResume:
    skills_by_category: dict[str, list[str]]
    experiences: tuple[object, ...] = ()
    target_role: str = ""
    job_context: object | None = None


@dataclass(frozen=True)
class _DummyBullet:
    skills: tuple[str, ...]


@dataclass(frozen=True)
class _DummyExperience:
    related_skills: tuple[str, ...]
    bullets: tuple[_DummyBullet, ...]


@dataclass(frozen=True)
class _DummyJobContext:
    role_hint: str = ""
    description_excerpt: str = ""
    company_research: object | None = None


@dataclass(frozen=True)
class _DummyCompanyResearch:
    industry_hint: str = ""


def test_prioritize_skills_by_importance_uses_frequency_and_role_relevance() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Languages": ["Python", "Java", "Kotlin"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("Java", "Java", "Python"),
                bullets=(
                    _DummyBullet(skills=("Java", "Kotlin")),
                    _DummyBullet(skills=("Java",)),
                    _DummyBullet(skills=("Python",)),
                ),
            ),
        ),
        target_role="Senior Java Engineer",
    )

    prioritized = prioritize_skills_by_importance(resume)
    assert prioritized["Languages"] == ["Java", "Python", "Kotlin"]


def test_prioritize_skills_by_importance_prefers_shorter_skill_when_scores_are_equal() -> (
    None
):
    resume = _DummyResume(
        skills_by_category={
            "Integration": [
                "Enterprise Service Bus Integration Automation",
                "API",
            ]
        }
    )

    prioritized = prioritize_skills_by_importance(resume)
    assert prioritized["Integration"] == [
        "API",
        "Enterprise Service Bus Integration Automation",
    ]


def test_prioritize_skills_by_importance_warns_for_unknown_signal_skills(
    caplog: pytest.LogCaptureFixture,
) -> None:
    resume = _DummyResume(
        skills_by_category={"Languages": ["Python"]},
        experiences=(
            _DummyExperience(
                related_skills=("Cobol",),
                bullets=(_DummyBullet(skills=("Cobol",)),),
            ),
        ),
    )

    caplog.set_level(logging.WARNING)
    prioritize_skills_by_importance(resume)

    assert any(
        "ignored unknown skills not present in skills matrix" in record.getMessage()
        for record in caplog.records
    )


def test_cap_skills_by_score_keeps_top_n() -> None:
    skills_by_category = {
        "Languages": ["Python", "Java"],
        "Testing": ["Pytest", "Selenium"],
        "Platforms": ["AWS"],
    }
    scores = {
        "Python": 9.0,
        "Selenium": 8.0,
        "AWS": 7.0,
        "Java": 6.0,
        "Pytest": 5.0,
    }

    capped = cap_skills_by_score(skills_by_category, scores, top_n=3)

    assert sum(len(skills) for skills in capped.values()) == 3
    assert capped == {
        "Languages": ["Python"],
        "Testing": ["Selenium"],
        "Platforms": ["AWS"],
    }


def test_cap_skills_by_score_drops_empty_categories() -> None:
    skills_by_category = {
        "Languages": ["Python"],
        "Testing": ["Pytest"],
        "Platforms": ["AWS"],
    }
    scores = {"Python": 9.0, "AWS": 8.0, "Pytest": 1.0}

    capped = cap_skills_by_score(skills_by_category, scores, top_n=2)

    assert capped == {
        "Languages": ["Python"],
        "Platforms": ["AWS"],
    }


def test_compute_skill_scores_includes_matrix_skills_without_usage_signals() -> None:
    """Skills absent from all bullets/related_skills still get a role-relevance score.

    Regression for Issue #97 Option A: before this fix, skills not in any
    experience entry fell back to 0.0 in the score map, causing the top-N cap
    to keep them in arbitrary CSV order instead of by relevance.
    """
    resume = _DummyResume(
        skills_by_category={
            "Platforms": ["AWS", "GCP", "Azure"],
        },
        target_role="AWS cloud engineer",
        experiences=(),
    )

    scores = _compute_skill_scores(resume)

    # All matrix skills must be present in the score map.
    assert "AWS" in scores
    assert "GCP" in scores
    assert "Azure" in scores
    # The role-relevant skill (AWS) must outrank the others.
    assert scores["AWS"] > scores["GCP"]
    assert scores["AWS"] > scores["Azure"]


def test_normalize_skill_near_dupes_keeps_highest_scored_variant() -> None:
    skills_by_category = {
        "Automation": ["CI/CD", "Playwright"],
        "Tooling": ["CI / CD", "GitHub Actions"],
    }
    scores = {
        "CI/CD": 2.0,
        "CI / CD": 9.0,
        "Playwright": 4.0,
        "GitHub Actions": 3.0,
    }

    normalized = normalize_skill_near_dupes(skills_by_category, scores)

    assert normalized == {
        "Automation": ["Playwright"],
        "Tooling": ["CI / CD", "GitHub Actions"],
    }


def test_normalize_skill_near_dupes_prefers_shorter_variant_on_score_tie() -> None:
    skills_by_category = {
        "Tooling": ["CI / CD", "CI/CD", "Jenkins"],
    }
    scores = {
        "CI / CD": 5.0,
        "CI/CD": 5.0,
        "Jenkins": 1.0,
    }

    normalized = normalize_skill_near_dupes(skills_by_category, scores)

    assert normalized == {
        "Tooling": ["CI/CD", "Jenkins"],
    }


def _role_relevance(skill: str, jd_text: str) -> float:
    role_text = jd_text.lower()
    expanded = _expand_jd_forms(_tokenize_role_text(role_text))
    return _skill_role_relevance(skill, role_text, expanded)


def test_skill_role_relevance_matches_dotted_variant_against_no_dot_jd() -> None:
    # Issue #184: H.323 in matrix vs H323 in JD must score full overlap.
    relevance = _role_relevance("H.323", "Need experience with H323 video stacks")
    assert relevance == pytest.approx(1.0)


def test_skill_role_relevance_matches_no_dot_skill_against_dotted_jd() -> None:
    relevance = _role_relevance("H323", "Need experience with H.323 video stacks")
    assert relevance == pytest.approx(1.0)


def test_skill_role_relevance_matches_hyphenated_skill_against_spaced_jd() -> None:
    # Issue #184: Multi-protocol Interop vs "multi protocol interop" must hit 1.0.
    relevance = _role_relevance(
        "Multi-protocol Interop", "Looking for multi protocol interop background"
    )
    assert relevance == pytest.approx(1.0)


def test_skill_role_relevance_matches_alias_no_separator_for_cicd() -> None:
    # Issue #184: CICD in JD must reach the CI/CD skill via alias canonicalization.
    relevance = _role_relevance("CI/CD", "Modern CICD pipelines required")
    assert relevance == pytest.approx(1.0)


def test_skill_role_relevance_does_not_invent_matches_for_unrelated_skills() -> None:
    # Regression guard: AWS-only JD must not score GCP / Azure above zero.
    role_text = "aws cloud engineer"
    expanded = _expand_jd_forms(_tokenize_role_text(role_text))
    assert _skill_role_relevance("AWS", role_text, expanded) > 1.0
    assert _skill_role_relevance("GCP", role_text, expanded) == 0.0
    assert _skill_role_relevance("Azure", role_text, expanded) == 0.0


def test_skill_role_relevance_split_subtokens_require_all_present() -> None:
    # Review feedback (PR #189): hyphenated skill must NOT match a JD that
    # only contains one half. `multi` alone should not pull in
    # `Multi-protocol Interop` via the split-subtoken path.
    relevance = _role_relevance(
        "Multi-protocol Interop", "experience with multi tenant systems"
    )
    # `interop` not in JD; `multi-protocol` only matches if BOTH `multi` and
    # `protocol` are present, which they are not.
    assert relevance == pytest.approx(0.0)


def test_skill_role_relevance_ignores_numeric_only_subtoken_collisions() -> None:
    # Review feedback (PR #189): split-subtoken path must reject numeric-only
    # fragments so `H.323` does not match a JD that incidentally contains 323.
    relevance = _role_relevance("H.323", "ticket 323 has been triaged")
    assert relevance == pytest.approx(0.0)


def test_normalize_skill_near_dupe_key_collapses_h323_punctuation_variants() -> None:
    assert _normalize_skill_near_dupe_key("H.323") == _normalize_skill_near_dupe_key(
        "H323"
    )


def test_compute_skill_scores_includes_role_relevant_matrix_only_skills() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Architecture": ["Fraud Analytics", "Payments APIs"],
        },
        target_role="Senior SDET",
        job_context=_DummyJobContext(
            description_excerpt="Need fraud analytics and payments APIs experience."
        ),
    )

    scores = _compute_skill_scores(resume)

    assert scores["Fraud Analytics"] > 0.0
    assert scores["Payments APIs"] > 0.0


def test_select_skills_returns_new_dataclass_and_keeps_source_immutable() -> None:
    original = {
        "Automation": [f"skill_{idx}" for idx in range(40)],
        "Delivery": [f"delivery_{idx}" for idx in range(40)],
    }
    resume = _DummyResume(skills_by_category=original)
    packed_resume = select_skills(resume)
    assert packed_resume is not resume
    assert isinstance(packed_resume, _DummyResume)
    assert resume.skills_by_category == original


def test_select_skills_applies_top_n_cap_before_trimming() -> None:
    captured: dict[str, list[str]] = {}
    all_skills = [f"skill_{idx:02d}" for idx in range(TOP_N_SKILLS + 5)]
    resume = _DummyResume(
        skills_by_category={
            "Everything": all_skills,
        },
        experiences=(
            _DummyExperience(
                related_skills=tuple(all_skills[:TOP_N_SKILLS]),
                bullets=tuple(
                    _DummyBullet(skills=(skill,)) for skill in all_skills[:TOP_N_SKILLS]
                ),
            ),
        ),
    )

    def fake_pack_skills_to_budget(
        skills_by_category: dict[str, list[str]], **_kwargs: object
    ) -> dict[str, list[str]]:
        captured.update(
            {category: list(skills) for category, skills in skills_by_category.items()}
        )
        return {
            category: list(skills) for category, skills in skills_by_category.items()
        }

    original_pack = select_skills_module.pack_skills_to_budget
    select_skills_module.pack_skills_to_budget = fake_pack_skills_to_budget
    try:
        packed_resume = select_skills(resume)
    finally:
        select_skills_module.pack_skills_to_budget = original_pack

    assert captured
    assert sum(len(skills) for skills in captured.values()) <= TOP_N_SKILLS
    assert set(all_skills[TOP_N_SKILLS:]).isdisjoint(
        skill for skills in captured.values() for skill in skills
    )
    assert len(packed_resume.skills_by_category["Everything"]) <= TOP_N_SKILLS
    assert set(all_skills[TOP_N_SKILLS:]).isdisjoint(
        packed_resume.skills_by_category["Everything"]
    )


def test_select_skills_normalizes_ci_cd_near_duplicates() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Automation": ["CI/CD", "Playwright"],
            "Tooling": ["CI / CD", "GitHub Actions"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("CI / CD",),
                bullets=(
                    _DummyBullet(skills=("CI / CD",)),
                    _DummyBullet(skills=("Playwright",)),
                ),
            ),
        ),
    )

    packed_resume = select_skills(resume)
    flattened = [
        skill
        for category_skills in packed_resume.skills_by_category.values()
        for skill in category_skills
    ]

    assert "CI / CD" in flattened
    assert "CI/CD" not in flattened


def test_select_skills_caps_unique_skills_after_normalizing_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(select_skills_module, "TOP_N_SKILLS", 3)
    monkeypatch.setattr(
        select_skills_module,
        "pack_skills_to_budget",
        lambda skills_by_category, **_kwargs: {
            category: list(skills) for category, skills in skills_by_category.items()
        },
    )

    resume = _DummyResume(
        skills_by_category={
            "Automation": ["CI/CD", "CI / CD", "Playwright", "GitHub Actions"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("CI / CD", "Playwright", "GitHub Actions"),
                bullets=(
                    _DummyBullet(skills=("CI / CD",)),
                    _DummyBullet(skills=("Playwright",)),
                    _DummyBullet(skills=("GitHub Actions",)),
                ),
            ),
        ),
    )

    packed_resume = select_skills(resume)
    flattened = [
        skill
        for category_skills in packed_resume.skills_by_category.values()
        for skill in category_skills
    ]

    assert flattened == ["CI / CD", "Playwright", "GitHub Actions"]


def test_select_skills_applies_importance_order_before_trimming() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Languages": ["Kotlin", "Python", "Java"],
            "Automation": ["Playwright", "Selenium", "Pytest"],
            "Platforms": ["Linux", "Docker", "Kubernetes"],
            "Tooling": ["CI/CD", "GitHub Actions", "Jenkins"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("Java", "Java", "Python"),
                bullets=(
                    _DummyBullet(skills=("Java",)),
                    _DummyBullet(skills=("Java", "CI/CD")),
                    _DummyBullet(skills=("Java", "Python")),
                ),
            ),
        ),
        target_role="Senior Java Engineer",
        job_context=_DummyJobContext(description_excerpt="Java backend testing CI/CD"),
    )

    packed_resume = select_skills(resume)
    ordered_languages = packed_resume.skills_by_category.get("Languages", [])
    assert ordered_languages
    assert ordered_languages[0] == "Java"


def test_select_skills_orders_categories_by_aggregate_role_relevance() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Platforms": ["Linux", "Docker", "Kubernetes"],
            "Languages": ["Kotlin", "Python", "Java"],
            "Tooling": ["CI/CD", "GitHub Actions", "Jenkins"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("Java", "Java", "Python", "CI/CD"),
                bullets=(
                    _DummyBullet(skills=("Java",)),
                    _DummyBullet(skills=("Java", "Python")),
                    _DummyBullet(skills=("CI/CD",)),
                ),
            ),
        ),
        target_role="Senior Java Engineer",
        job_context=_DummyJobContext(description_excerpt="Java backend testing CI/CD"),
    )

    packed_resume = select_skills(resume)

    assert list(packed_resume.skills_by_category) == [
        "Languages",
        "Tooling",
        "Platforms",
    ]


def test_select_skills_applies_hybrid_industry_weighting_for_categories() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Programming & Scripting": ["Python", "Java"],
            "Security & Compliance": ["Threat Modeling", "SOC2"],
            "CI/CD & Tooling": ["GitHub Actions", "Jenkins"],
        },
        experiences=(
            _DummyExperience(
                related_skills=("Java",),
                bullets=(
                    _DummyBullet(skills=("Java",)),
                    _DummyBullet(skills=("Python",)),
                ),
            ),
        ),
        target_role="Software Engineer",
        job_context=_DummyJobContext(
            description_excerpt="payments risk controls and compliance automation",
            company_research=_DummyCompanyResearch(industry_hint="Financial services"),
        ),
    )

    packed_resume = select_skills(resume)

    assert list(packed_resume.skills_by_category)[0] == "Security & Compliance"


def test_compute_category_industry_weights_fails_open_for_unknown_industry() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Programming & Scripting": ["Python"],
            "Security & Compliance": ["Threat Modeling"],
        },
        job_context=_DummyJobContext(
            description_excerpt="domain specific requirements",
            company_research=_DummyCompanyResearch(industry_hint="Unknown domain"),
        ),
    )

    category_weights = _compute_category_industry_weights(
        resume,
        skills_by_category=resume.skills_by_category,
    )

    assert category_weights == {
        "Programming & Scripting": 0.0,
        "Security & Compliance": 0.0,
    }


def test_compute_category_industry_weights_ignores_generic_zero_phrase() -> None:
    resume = _DummyResume(
        skills_by_category={
            "Security & Compliance": ["Threat Modeling"],
            "Platforms": ["Linux"],
        },
        job_context=_DummyJobContext(
            description_excerpt="platform reliability with zero downtime targets",
        ),
    )

    category_weights = _compute_category_industry_weights(
        resume,
        skills_by_category=resume.skills_by_category,
    )

    assert category_weights == {
        "Security & Compliance": 0.0,
        "Platforms": 0.0,
    }


def test_compute_category_industry_weights_jd_boost_uses_jd_excerpt_only() -> None:
    shared_skills = {"Security & Compliance": ["Threat Modeling"]}

    role_only_resume = _DummyResume(
        skills_by_category=shared_skills,
        target_role="Compliance Engineer",
        job_context=_DummyJobContext(
            description_excerpt="backend platform services",
            company_research=_DummyCompanyResearch(industry_hint="Financial services"),
        ),
    )
    role_only_weights = _compute_category_industry_weights(
        role_only_resume,
        skills_by_category=role_only_resume.skills_by_category,
    )

    jd_resume = _DummyResume(
        skills_by_category=shared_skills,
        target_role="Compliance Engineer",
        job_context=_DummyJobContext(
            description_excerpt="backend platform services with compliance controls",
            company_research=_DummyCompanyResearch(industry_hint="Financial services"),
        ),
    )
    jd_weights = _compute_category_industry_weights(
        jd_resume,
        skills_by_category=jd_resume.skills_by_category,
    )

    assert (
        jd_weights["Security & Compliance"] > role_only_weights["Security & Compliance"]
    )
