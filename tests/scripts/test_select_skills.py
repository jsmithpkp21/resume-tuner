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
    _section_layout,
    _wrap_widths,
    estimate_line_count,
    join_skills,
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
