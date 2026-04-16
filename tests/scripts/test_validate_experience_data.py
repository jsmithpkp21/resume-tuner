from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validate_experience_data import (
    has_measurable_outcome,
    load_skills_matrix,
    validate_experience_data,
)

VALID_SKILLS = {"Python", "CI/CD", "Java"}


def test_load_skills_matrix_reads_utf8_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "skills_matrix.csv"
    csv_path.write_text(
        'Skills,Category\n"Python","Language"\n"Cafe Testing","QA"\n',
        encoding="utf-8",
        newline="",
    )

    assert load_skills_matrix(csv_path) == {"Python", "Cafe Testing"}


def _experience_payload(
    *,
    impact_type: str = "reliability",
    domain: str | None = "video",
    text: str = "Reduced flaky failures by 30 percent in CI.",
) -> dict[str, Any]:
    bullet: dict[str, Any] = {
        "id": "bullet_1",
        "text": text,
        "skills": ["Python"],
        "impact_type": impact_type,
    }
    if domain is not None:
        bullet["domain"] = domain

    return {
        "experience": [
            {
                "id": "exp_1",
                "related_skills": ["Python"],
                "bullet_bank": [bullet],
            }
        ]
    }


def test_validate_experience_data_flags_invalid_impact_type() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(impact_type="invalid-impact", domain="video"), VALID_SKILLS
    )

    assert errors == ["bullet_1: invalid impact_type 'invalid-impact'"]
    assert warnings == []


def test_validate_experience_data_flags_invalid_related_skill() -> None:
    payload = _experience_payload(impact_type="reliability", domain="video")
    payload["experience"][0]["related_skills"] = ["Cobol"]

    errors, warnings = validate_experience_data(payload, VALID_SKILLS)

    assert errors == ["exp_1: related_skill 'Cobol' not in skills matrix"]
    assert warnings == []


def test_validate_experience_data_warns_when_domain_missing() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(impact_type="reliability", domain=None), VALID_SKILLS
    )

    assert errors == []
    assert warnings == ["bullet_1: missing 'domain' field"]


def test_validate_experience_data_warns_when_bullet_lacks_measurable_outcome() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(
            impact_type="reliability",
            domain="video",
            text="Improved framework readability and structure.",
        ),
        VALID_SKILLS,
    )

    assert errors == []
    assert warnings == ["bullet_1: consider adding measurable outcome language"]


def test_validate_experience_data_passes_for_valid_payload() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(impact_type="scalability", domain="audio"), VALID_SKILLS
    )

    assert errors == []
    assert warnings == []


def test_has_measurable_outcome_accepts_percent_and_multiplier_patterns() -> None:
    assert has_measurable_outcome("Reduced runtime by 25 percent")
    assert has_measurable_outcome("Improved throughput 2x")
    assert not has_measurable_outcome("Improved readability and maintainability")
