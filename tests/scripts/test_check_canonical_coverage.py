"""Tests for the worksheet-independent canonical coverage check (issue #21)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resume_builder.check_canonical_coverage import (
    build_report,
    evaluate_hard_gates,
    load_experience_db,
    load_skills_matrix,
    main,
    write_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_skills(path: Path, skills: list[str]) -> None:
    rows = ["Skills,Category"]
    rows.extend(f'"{skill}","Cat"' for skill in skills)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _bullet(bullet_id: str, skills: list[str]) -> str:
    skills_repr = ", ".join(f'"{s}"' for s in skills)
    return (
        "[[experience.bullet_bank]]\n"
        f'id = "{bullet_id}"\n'
        'text = "Did the thing measurably 50 percent better."\n'
        f"skills = [{skills_repr}]\n"
        'impact_type = "reliability"\n'
        'domain = "video"\n'
    )


def _experience_block(
    *,
    exp_id: str = "exp_a",
    grd: str = "Did important work.",
    bullets: int = 3,
    skills_per_bullet: list[str] | None = None,
) -> str:
    skills_per_bullet = skills_per_bullet or ["Python"]
    blocks = [
        "[[experience]]",
        f'id = "{exp_id}"',
        f'general_role_description = "{grd}"',
        'related_skills = ["Python"]',
        "related_skills_inferred = []",
        "",
    ]
    for i in range(bullets):
        blocks.append(_bullet(f"{exp_id}_b{i:02d}", skills_per_bullet))
    return "\n".join(blocks)


def _write_experience_db(path: Path, body: str) -> None:
    path.write_text(
        '[metadata]\nschema_version = "1"\n\n' + body,
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


def test_load_skills_matrix_returns_unique_skills(tmp_path: Path) -> None:
    csv_path = tmp_path / "skills.csv"
    _write_skills(csv_path, ["Python", "Java", "Python"])
    assert load_skills_matrix(csv_path) == {"Python", "Java"}


def test_load_experience_db_returns_experience_list(tmp_path: Path) -> None:
    db_path = tmp_path / "experience_db.toml"
    _write_experience_db(db_path, _experience_block())
    experiences = load_experience_db(db_path)
    assert len(experiences) == 1
    assert experiences[0]["id"] == "exp_a"


# ---------------------------------------------------------------------------
# Hard-gate failure cases
# ---------------------------------------------------------------------------


def test_missing_general_role_description_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block(grd=""))
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])

    report = build_report(db_path, skills_path)

    gates = {f.gate for f in report.hard_gate_failures}
    assert "missing_general_role_description" in gates


def test_below_minimum_bullets_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block(bullets=2))
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])

    report = build_report(db_path, skills_path)

    gates = {f.gate for f in report.hard_gate_failures}
    assert "bullet_bank_below_minimum" in gates


def test_unknown_skill_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(
        db_path, _experience_block(skills_per_bullet=["Python", "MysterySkill"])
    )
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])

    report = build_report(db_path, skills_path)

    failures = [
        f for f in report.hard_gate_failures if f.gate == "bullet_skill_not_in_matrix"
    ]
    assert failures, "expected at least one unknown-skill failure"
    assert any("MysterySkill" in f.detail for f in failures)


def test_clean_canonical_data_passes(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block())
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])

    report = build_report(db_path, skills_path)

    assert report.hard_gate_failures == []
    assert report.experience_count == 1
    assert report.bullet_count == 3


def test_unknown_related_skill_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    body = _experience_block().replace(
        'related_skills = ["Python"]',
        'related_skills = ["Python", "GhostRoleSkill"]',
    )
    _write_experience_db(db_path, body)
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])

    report = build_report(db_path, skills_path)

    failures = [
        f for f in report.hard_gate_failures if f.gate == "related_skill_not_in_matrix"
    ]
    assert failures, "expected at least one unknown-related-skill failure"
    assert any("GhostRoleSkill" in f.detail for f in failures)


# ---------------------------------------------------------------------------
# Report shape contract
# ---------------------------------------------------------------------------


def test_report_to_dict_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block())
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python", "Unused"])

    report = build_report(db_path, skills_path).to_dict()

    expected_keys = {
        "generated_at",
        "inputs",
        "experience_count",
        "bullet_count",
        "bullets_per_role",
        "skills_matrix_size",
        "skills_referenced",
        "skills_unreferenced",
        "roles_missing_related_skills",
        "hard_gate_failures",
    }
    assert expected_keys <= report.keys()
    bpr = report["bullets_per_role"]
    assert {"min", "max", "median", "mean", "histogram"} <= bpr.keys()
    assert report["skills_matrix_size"] == 2
    assert report["skills_referenced"] == 1
    assert report["skills_unreferenced"] == 1


# ---------------------------------------------------------------------------
# CLI behavior
# ---------------------------------------------------------------------------


def test_main_strict_returns_nonzero_when_gate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block(bullets=1))
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])
    output_path = tmp_path / "coverage.json"

    rc = main(
        [
            "--experience-db",
            str(db_path),
            "--skills-matrix",
            str(skills_path),
            "--output",
            str(output_path),
            "--strict",
        ]
    )

    assert rc == 1
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["hard_gate_failures"], "report should record the failure"


def test_write_report_rejects_blocked_sandbox_output(tmp_path: Path) -> None:
    """`write_report` refuses to write into ``sandbox/`` (#20 guard).

    Inputs are guarded by the loaders; outputs need the same protection so
    ``--output sandbox/coverage.json`` cannot exfiltrate the report.
    """
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block())
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])
    blocked_output = REPO_ROOT / "sandbox" / "coverage.json"
    if blocked_output.exists():
        pytest.skip("Unexpected collision with existing sandbox file")

    report = build_report(db_path, skills_path)
    with pytest.raises(ValueError, match="blocked runtime directory"):
        write_report(report, blocked_output)
    assert not blocked_output.exists()


def test_write_report_rejects_blocked_samples_output(tmp_path: Path) -> None:
    """`write_report` refuses to write into ``data/samples/`` (#20 guard)."""
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block())
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])
    blocked_output = REPO_ROOT / "data" / "samples" / "coverage.json"
    if blocked_output.exists():
        pytest.skip("Unexpected collision with existing samples file")

    report = build_report(db_path, skills_path)
    with pytest.raises(ValueError, match="blocked runtime directory"):
        write_report(report, blocked_output)
    assert not blocked_output.exists()


def test_main_non_strict_returns_zero_even_when_gate_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db_path = tmp_path / "db.toml"
    _write_experience_db(db_path, _experience_block(bullets=1))
    skills_path = tmp_path / "skills.csv"
    _write_skills(skills_path, ["Python"])
    output_path = tmp_path / "coverage.json"

    rc = main(
        [
            "--experience-db",
            str(db_path),
            "--skills-matrix",
            str(skills_path),
            "--output",
            str(output_path),
        ]
    )

    assert rc == 0


# ---------------------------------------------------------------------------
# Real-data smoke test
# ---------------------------------------------------------------------------


def test_real_canonical_data_passes_strict_gates(tmp_path: Path) -> None:
    """Sanity check: today's canonical data should already satisfy hard gates.

    Gates mirror existing DESIGN.md invariants enforced by validate_experience_data,
    so a failure here means either the canonical data regressed or this script
    drifted from the design.
    """
    output_path = tmp_path / "coverage.json"
    rc = main(
        [
            "--experience-db",
            str(REPO_ROOT / "data" / "experience" / "experience_db.toml"),
            "--skills-matrix",
            str(REPO_ROOT / "data" / "skills" / "skills_matrix.csv"),
            "--output",
            str(output_path),
            "--strict",
        ]
    )
    assert rc == 0, output_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# evaluate_hard_gates direct call
# ---------------------------------------------------------------------------


def test_evaluate_hard_gates_reports_each_failure_independently() -> None:
    experiences = [
        {
            "id": "exp_a",
            "general_role_description": "",
            "related_skills": ["GhostRoleSkill"],
            "bullet_bank": [
                {"id": "exp_a_b0", "skills": ["Python"]},
                {"id": "exp_a_b1", "skills": ["GhostSkill"]},
            ],
        },
    ]
    skills = {"Python"}

    failures = evaluate_hard_gates(experiences, skills)
    gates = sorted(f.gate for f in failures)
    assert gates == [
        "bullet_bank_below_minimum",
        "bullet_skill_not_in_matrix",
        "missing_general_role_description",
        "related_skill_not_in_matrix",
    ]
