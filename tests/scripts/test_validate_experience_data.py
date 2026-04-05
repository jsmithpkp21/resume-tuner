from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.validate_experience_data import (
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
    *, impact_type: str = "reliability", domain: str | None = "video"
) -> dict[str, Any]:
    bullet: dict[str, Any] = {
        "id": "bullet_1",
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


def test_validate_experience_data_warns_when_domain_missing() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(impact_type="reliability", domain=None), VALID_SKILLS
    )

    assert errors == []
    assert warnings == ["bullet_1: missing 'domain' field"]


def test_validate_experience_data_passes_for_valid_payload() -> None:
    errors, warnings = validate_experience_data(
        _experience_payload(impact_type="scalability", domain="audio"), VALID_SKILLS
    )

    assert errors == []
    assert warnings == []
