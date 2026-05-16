from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from resume_builder.measurable_outcomes import has_measurable_outcome
from resume_builder.validate_experience_data import (
    load_experience_db,
    load_skills_matrix,
    validate_experience_data,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

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
    assert has_measurable_outcome(
        "Reducing duplicate framework spike efforts by forty percent across teams"
    )
    assert has_measurable_outcome(
        "Eliminating manual release tagging across fifteen projects"
    )
    assert not has_measurable_outcome("Improved readability and maintainability")


def test_validate_experience_data_ignores_blank_or_none_like_text_values() -> None:
    payload = {
        "experience": [
            {
                "id": "exp_1",
                "related_skills": ["Python"],
                "bullet_bank": [
                    {
                        "id": "bullet_1",
                        "text": None,
                        "skills": ["Python"],
                        "impact_type": "reliability",
                        "domain": "video",
                    },
                    {
                        "id": "bullet_2",
                        "text": "   ",
                        "skills": ["Python"],
                        "impact_type": "reliability",
                        "domain": "video",
                    },
                ],
            }
        ]
    }

    errors, warnings = validate_experience_data(payload, VALID_SKILLS)

    assert errors == []
    assert warnings == []


# ---------------------------------------------------------------------------
# load_experience_db
# ---------------------------------------------------------------------------


def test_load_experience_db_parses_toml(tmp_path: Path) -> None:
    """`load_experience_db` returns the parsed TOML dict."""
    toml_path = tmp_path / "experience_db.toml"
    toml_path.write_text(
        '[[experience]]\nid = "exp_1"\nrelated_skills = ["Python"]\n',
        encoding="utf-8",
    )

    data = load_experience_db(toml_path)

    assert data["experience"][0]["id"] == "exp_1"
    assert data["experience"][0]["related_skills"] == ["Python"]


def test_load_experience_db_rejects_blocked_runtime_path() -> None:
    """Honors the shared blocked-runtime-roots guard."""
    blocked = REPO_ROOT / "sandbox" / "experience_db.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_experience_db(blocked)


# ---------------------------------------------------------------------------
# validate_experience_data — bullet-level skill validation
# ---------------------------------------------------------------------------


def test_validate_experience_data_flags_invalid_bullet_skill() -> None:
    """Bullets that list a skill outside the matrix produce a per-bullet error."""
    payload = _experience_payload(impact_type="reliability", domain="video")
    payload["experience"][0]["bullet_bank"][0]["skills"] = ["Cobol"]

    errors, warnings = validate_experience_data(payload, VALID_SKILLS)

    assert "bullet_1: skill 'Cobol' not in skills matrix" in errors
    assert warnings == []


def test_validate_experience_data_accepts_payload_with_no_experience_key() -> None:
    """Missing `experience` key short-circuits cleanly (no errors, no warnings)."""
    errors, warnings = validate_experience_data({}, VALID_SKILLS)
    assert errors == []
    assert warnings == []


# ---------------------------------------------------------------------------
# main() CLI surface
# ---------------------------------------------------------------------------


def test_main_returns_nonzero_when_experience_db_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main` returns 1 with a clear stderr when experience_db.toml is missing.

    Patched via working directory: the script resolves paths relative to a
    fixed `parents[2]` (its real install location), so we exercise the
    file-missing branch by mocking the imported `Path` inside the module.
    """
    from resume_builder import validate_experience_data as mod

    # Repoint the project root by patching how `main` derives it.
    fake_root = tmp_path
    (fake_root / "data" / "experience").mkdir(parents=True)
    (fake_root / "data" / "skills").mkdir(parents=True)

    monkeypatch.setattr(
        mod,
        "__file__",
        str(fake_root / "src" / "resume_builder" / "validate_experience_data.py"),
    )

    rc = mod.main()
    assert rc == 1


def test_main_succeeds_on_valid_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path: valid TOML + matching skills matrix → exit 0 and success print."""
    from resume_builder import validate_experience_data as mod

    (tmp_path / "data" / "experience").mkdir(parents=True)
    (tmp_path / "data" / "skills").mkdir(parents=True)

    (tmp_path / "data" / "experience" / "experience_db.toml").write_text(
        """
[[experience]]
id = "exp_1"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Reduced runtime by 25 percent in CI."
skills = ["Python"]
impact_type = "reliability"
domain = "video"
""",
        encoding="utf-8",
    )
    (tmp_path / "data" / "skills" / "skills_matrix.csv").write_text(
        "Skills,Category\nPython,Language\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mod,
        "__file__",
        str(tmp_path / "src" / "resume_builder" / "validate_experience_data.py"),
    )

    rc = mod.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "All validations passed" in captured.out


def test_main_returns_zero_when_only_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Warnings alone (no errors) keep the exit code at 0; banner appears in stdout."""
    from resume_builder import validate_experience_data as mod

    (tmp_path / "data" / "experience").mkdir(parents=True)
    (tmp_path / "data" / "skills").mkdir(parents=True)

    # Bullet missing 'domain' → warning, no error
    (tmp_path / "data" / "experience" / "experience_db.toml").write_text(
        """
[[experience]]
id = "exp_1"
related_skills = ["Python"]

[[experience.bullet_bank]]
id = "b1"
text = "Reduced runtime by 25 percent in CI."
skills = ["Python"]
impact_type = "reliability"
""",
        encoding="utf-8",
    )
    (tmp_path / "data" / "skills" / "skills_matrix.csv").write_text(
        "Skills,Category\nPython,Language\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mod,
        "__file__",
        str(tmp_path / "src" / "resume_builder" / "validate_experience_data.py"),
    )

    rc = mod.main()
    captured = capsys.readouterr()
    assert rc == 0
    assert "WARNINGS" in captured.out


def test_main_returns_one_when_errors_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Errors flip the exit code to 1 and surface the ERRORS banner."""
    from resume_builder import validate_experience_data as mod

    (tmp_path / "data" / "experience").mkdir(parents=True)
    (tmp_path / "data" / "skills").mkdir(parents=True)

    # related_skill 'Cobol' is not in the skills matrix → error
    (tmp_path / "data" / "experience" / "experience_db.toml").write_text(
        """
[[experience]]
id = "exp_1"
related_skills = ["Cobol"]
""",
        encoding="utf-8",
    )
    (tmp_path / "data" / "skills" / "skills_matrix.csv").write_text(
        "Skills,Category\nPython,Language\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        mod,
        "__file__",
        str(tmp_path / "src" / "resume_builder" / "validate_experience_data.py"),
    )

    rc = mod.main()
    captured = capsys.readouterr()
    assert rc == 1
    assert "ERRORS" in captured.out


def test_main_returns_one_when_skills_matrix_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """experience_db.toml present but skills_matrix.csv missing → rc=1."""
    from resume_builder import validate_experience_data as mod

    (tmp_path / "data" / "experience").mkdir(parents=True)
    (tmp_path / "data" / "experience" / "experience_db.toml").write_text(
        '[[experience]]\nid = "exp_1"\n', encoding="utf-8"
    )
    # NOTE: no skills_matrix.csv

    monkeypatch.setattr(
        mod,
        "__file__",
        str(tmp_path / "src" / "resume_builder" / "validate_experience_data.py"),
    )

    rc = mod.main()
    assert rc == 1
