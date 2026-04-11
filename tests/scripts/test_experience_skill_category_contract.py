from __future__ import annotations

import csv
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_CSV = REPO_ROOT / "data" / "skills" / "skills_matrix.csv"
EXPERIENCE_TOML = REPO_ROOT / "data" / "experience" / "experience_db.toml"


def _load_skill_to_category() -> dict[str, str]:
    mapping: dict[str, str] = {}
    with SKILLS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert "Skills" in reader.fieldnames and "Category" in reader.fieldnames, (
            "skills_matrix.csv must include Skills and Category headers"
        )

        for idx, row in enumerate(reader, start=2):
            skill = (row.get("Skills") or "").strip()
            category = (row.get("Category") or "").strip()

            assert skill, f"Row {idx}: Skills must not be empty"
            assert category, f"Row {idx}: Category must not be empty"

            if skill in mapping:
                assert mapping[skill] == category, (
                    f"Skill '{skill}' maps to multiple categories: "
                    f"'{mapping[skill]}' and '{category}'"
                )
            mapping[skill] = category

    return mapping


def _load_experience() -> list[dict[str, Any]]:
    data = tomllib.loads(EXPERIENCE_TOML.read_text(encoding="utf-8"))
    exps = data.get("experience", [])
    assert isinstance(exps, list), (
        "experience_db.toml must contain [[experience]] entries"
    )
    return exps


def test_skills_matrix_has_single_nonempty_category_per_skill() -> None:
    mapping = _load_skill_to_category()
    assert mapping, "skills_matrix.csv must contain at least one skill"


def test_skills_matrix_no_case_insensitive_duplicates_within_category() -> None:
    """Guard against the same skill appearing twice under one category with different casing.

    Example violation: 'Automation strategy' and 'Automation Strategy' both mapped to
    'Automation & Framework Engineering' would be caught here.
    """
    category_to_lower: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []

    with SKILLS_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader, start=2):
            skill = (row.get("Skills") or "").strip()
            category = (row.get("Category") or "").strip()
            if not skill or not category:
                continue
            lower_key = skill.lower()
            seen = category_to_lower.setdefault(category, {})
            if lower_key in seen and seen[lower_key] != skill:
                duplicates.append(
                    f"Row {idx}: '{skill}' is a case variant of '{seen[lower_key]}' "
                    f"in category '{category}'"
                )
            else:
                seen[lower_key] = skill

    assert not duplicates, (
        "skills_matrix.csv contains case-insensitive duplicate skills within the same category:\n"
        + "\n".join(duplicates)
    )


def test_all_experience_bullet_skills_exist_in_skills_matrix() -> None:
    skill_map = _load_skill_to_category()
    experiences = _load_experience()

    missing: list[tuple[str, str]] = []
    for exp in experiences:
        exp_id = str(exp.get("id", "<missing-id>"))
        for bullet in exp.get("bullet_bank", []):
            for skill in bullet.get("skills", []):
                if skill not in skill_map:
                    missing.append((exp_id, skill))

    assert not missing, (
        "experience_db.toml references skills missing from skills_matrix.csv: "
        + ", ".join(f"{exp_id}:{skill}" for exp_id, skill in missing)
    )


def test_all_experience_related_skills_exist_in_skills_matrix() -> None:
    skill_map = _load_skill_to_category()
    experiences = _load_experience()

    missing: list[tuple[str, str]] = []
    for exp in experiences:
        exp_id = str(exp.get("id", "<missing-id>"))
        related_skills = exp.get("related_skills", [])
        assert isinstance(related_skills, list), (
            f"{exp_id}: related_skills must be a list"
        )
        assert all(
            isinstance(skill, str) and skill.strip() for skill in related_skills
        ), f"{exp_id}: related_skills entries must be non-empty strings"

        for skill in related_skills:
            if skill not in skill_map:
                missing.append((exp_id, skill))

    assert not missing, (
        "experience_db.toml related_skills references skills missing from skills_matrix.csv: "
        + ", ".join(f"{exp_id}:{skill}" for exp_id, skill in missing)
    )


def test_bullet_categories_if_present_are_nonempty_strings() -> None:
    experiences = _load_experience()
    for exp in experiences:
        exp_id = str(exp.get("id", "<missing-id>"))
        for idx, bullet in enumerate(exp.get("bullet_bank", []), start=1):
            categories = bullet.get("categories")
            if categories is None:
                continue
            assert isinstance(categories, list), (
                f"{exp_id} bullet #{idx}: categories must be a list when present"
            )
            assert all(isinstance(c, str) and c.strip() for c in categories), (
                f"{exp_id} bullet #{idx}: categories must be non-empty strings when present"
            )
