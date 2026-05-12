from __future__ import annotations

import csv
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from resume_builder.generate_review_packet import (
    bullet_skill_text_mismatch_skills,
    parse_note_reason_codes,
    read_csv_rows,
    read_experiences,
    read_notes,
    read_skills,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate_review_packet.py"


def test_generate_review_packet_outputs_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "packet"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    expected = {
        "readiness_summary.md",
        "findings.csv",
        "fix_queue.csv",
        "coverage_snapshot.json",
        "reviewer_notes_template.csv",
    }
    actual = {p.name for p in output_dir.iterdir()}
    assert expected.issubset(actual)
    with (output_dir / "findings.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    # Findings may be empty after all blockers/warnings are resolved; require schema either way.
    assert reader.fieldnames is not None
    assert "review_item_id" in reader.fieldnames
    assert all("review_item_id" in row for row in rows)

    with (output_dir / "fix_queue.csv").open(newline="", encoding="utf-8") as handle:
        queue_reader = csv.DictReader(handle)
        assert queue_reader.fieldnames is not None
        assert "note_reason_codes" in queue_reader.fieldnames


def test_read_csv_rows_with_non_blocked_temp_path(tmp_path: Path) -> None:
    """`read_csv_rows` works for non-blocked temp CSV paths."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name\n1,test\n", encoding="utf-8")
    rows = read_csv_rows(csv_file)
    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert rows[0]["name"] == "test"


def test_read_skills_with_non_blocked_temp_path(tmp_path: Path) -> None:
    """`read_skills` works for non-blocked temp skills files."""
    skills_file = tmp_path / "skills_matrix.csv"
    skills_file.write_text(
        "Skills,Category\nPython,Language\nDocker,DevOps\n",
        encoding="utf-8",
    )
    skills = read_skills(skills_file)
    assert "Python" in skills
    assert "Docker" in skills
    assert len(skills) == 2


def test_read_experiences_with_non_blocked_temp_path(tmp_path: Path) -> None:
    """`read_experiences` works for non-blocked temp TOML paths."""
    exp_file = tmp_path / "experience_db.toml"
    exp_file.write_text(
        '[[experience]]\nid = "exp_1"\ngeneral_role_description = "Test role"\nbullet_bank = []\n',
        encoding="utf-8",
    )
    experiences = read_experiences(exp_file)
    assert len(experiences) == 1
    assert experiences[0]["id"] == "exp_1"


def test_read_notes_rejects_blocked_path_before_write() -> None:
    """`read_notes` rejects blocked paths before mkdir/write side effects happen."""
    blocked_notes = REPO_ROOT / "sandbox" / f"notes_{uuid.uuid4().hex}.csv"
    if blocked_notes.exists():
        pytest.skip("Unexpected collision with existing sandbox notes file")
    with pytest.raises(ValueError, match="blocked runtime directory"):
        read_notes(blocked_notes)
    assert not blocked_notes.exists()


def test_read_csv_rows_rejects_blocked_sandbox_path() -> None:
    """`read_csv_rows` raises ValueError for paths rooted in `sandbox/`."""
    blocked_path = REPO_ROOT / "sandbox" / "worksheet.csv"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        read_csv_rows(blocked_path)


def test_read_csv_rows_rejects_blocked_samples_path() -> None:
    """`read_csv_rows` raises ValueError for paths rooted in `data/samples/`."""
    blocked_path = REPO_ROOT / "data" / "samples" / "worksheet.csv"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        read_csv_rows(blocked_path)


def test_read_experiences_rejects_blocked_sandbox_path() -> None:
    """`read_experiences` raises ValueError for paths rooted in `sandbox/`."""
    blocked_path = REPO_ROOT / "sandbox" / "experience_db.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        read_experiences(blocked_path)


def test_read_experiences_rejects_blocked_samples_path() -> None:
    """`read_experiences` raises ValueError for paths rooted in `data/samples/`."""
    blocked_path = REPO_ROOT / "data" / "samples" / "experience_db.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        read_experiences(blocked_path)


def test_generate_review_packet_without_sandbox_dependency(tmp_path: Path) -> None:
    """CLI succeeds with non-blocked temp inputs and no sandbox dependency."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    exp_dir = data_dir / "experience"
    exp_dir.mkdir()
    (exp_dir / "experience_db.toml").write_text(
        '[[experience]]\nid = "test_exp"\ngeneral_role_description = "Test"\nbullet_bank = []\n',
        encoding="utf-8",
    )
    (exp_dir / "experience_reconciliation_worksheet.csv").write_text(
        "id\n1\n",
        encoding="utf-8",
    )
    skills_dir = data_dir / "skills"
    skills_dir.mkdir()
    (skills_dir / "skills_matrix.csv").write_text(
        "Skills,Category\nPython,Language\n",
        encoding="utf-8",
    )
    review_dir = data_dir / "review"
    review_dir.mkdir()
    output_dir = tmp_path / "output"
    sandbox_dir = tmp_path / "sandbox"
    assert not sandbox_dir.exists()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--worksheet",
            str(exp_dir / "experience_reconciliation_worksheet.csv"),
            "--experience-db",
            str(exp_dir / "experience_db.toml"),
            "--skills-matrix",
            str(skills_dir / "skills_matrix.csv"),
            "--notes",
            str(review_dir / "reviewer_notes.csv"),
            "--output-dir",
            str(output_dir),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert output_dir.exists()
    assert (output_dir / "findings.csv").exists()


def test_bullet_skill_text_mismatch_skills_flags_only_high_signal_missing() -> None:
    bullet = {"skills": ["CI/CD", "Docker", "Developer Tooling"]}
    text = "Built shared helper code and pipeline workflows."
    assert bullet_skill_text_mismatch_skills(text, bullet) == ["Docker"]


def test_bullet_skill_text_mismatch_skills_no_false_positive_when_evidenced() -> None:
    bullet = {"skills": ["CI/CD", "GitHub Actions", "Docker"]}
    text = "Integrated Docker into an existing GitHub Actions pipeline for repeatable runs."
    assert bullet_skill_text_mismatch_skills(text, bullet) == []


def test_bullet_skill_text_mismatch_skills_embedded_substrings_do_not_count() -> None:
    bullet = {"skills": ["CI/CD"]}
    text = (
        "Built specific decision support helpers for release reviews, "
        "with pipeline automation for nightly gates."
    )
    assert bullet_skill_text_mismatch_skills(text, bullet) == []

    ci_cd_text = "CI/CD regression automation now runs in nightly gates."
    assert bullet_skill_text_mismatch_skills(ci_cd_text, bullet) == []

    bare_ci_text = (
        "Architected and drove Java migration, improving CI and automation stability."
    )
    assert bullet_skill_text_mismatch_skills(bare_ci_text, bullet) == []

    missing_text = "Built specific decision support helpers for release reviews."
    assert bullet_skill_text_mismatch_skills(missing_text, bullet) == ["CI/CD"]


def test_parse_note_reason_codes_for_will_not_fix() -> None:
    note = "source-lacks-quant; downstream-impact-unknown"
    assert (
        parse_note_reason_codes("will_not_fix", note)
        == "source-lacks-quant; downstream-impact-unknown"
    )


def test_parse_note_reason_codes_ignores_non_will_not_fix() -> None:
    assert parse_note_reason_codes("rewrite", "source-lacks-quant") == ""


def _run_cli_with_output_dir(output_dir: Path) -> subprocess.CompletedProcess[str]:
    """Invoke generate_review_packet.py CLI with the given --output-dir."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output_dir)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_main_rejects_output_dir_inside_sandbox() -> None:
    """`main` rejects `--output-dir sandbox/...` before any filesystem mutation."""
    blocked = REPO_ROOT / "sandbox" / f"review_packet_{uuid.uuid4().hex}"
    assert not blocked.exists()
    result = _run_cli_with_output_dir(blocked)
    assert result.returncode != 0, result.stdout
    assert "blocked runtime directory" in result.stderr, result.stderr
    assert not blocked.exists(), (
        f"output_dir {blocked} was created despite guard rejection"
    )


def test_main_rejects_output_dir_inside_data_samples() -> None:
    """`main` rejects `--output-dir data/samples/...` before any filesystem mutation."""
    blocked = REPO_ROOT / "data" / "samples" / f"review_packet_{uuid.uuid4().hex}"
    assert not blocked.exists()
    result = _run_cli_with_output_dir(blocked)
    assert result.returncode != 0, result.stdout
    assert "blocked runtime directory" in result.stderr, result.stderr
    assert not blocked.exists(), (
        f"output_dir {blocked} was created despite guard rejection"
    )
