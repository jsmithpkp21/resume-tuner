"""Tests for skills layout packing (Issue #42)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
    from select_skills import (
        MIN_SKILLS_PER_CATEGORY,
        TARGET_LINES_MAX,
        TARGET_LINES_MIN,
        _section_layout,
        estimate_line_count,
        pack_skills_to_budget,
        select_skills,
    )
else:
    from scripts.select_skills import (
        MIN_SKILLS_PER_CATEGORY,
        TARGET_LINES_MAX,
        TARGET_LINES_MIN,
        _section_layout,
        estimate_line_count,
        pack_skills_to_budget,
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


@dataclass(frozen=True)
class _DummyResume:
    skills_by_category: dict[str, list[str]]


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
