from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from scripts.generate_review_packet import read_csv_rows, read_experiences, read_skills

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


def test_read_csv_rows_with_canonical_path(tmp_path: Path) -> None:
    """read_csv_rows works with canonical data CSV."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name\n1,test\n", encoding="utf-8")

    rows = read_csv_rows(csv_file)
    assert len(rows) == 1
    assert rows[0]["id"] == "1"
    assert rows[0]["name"] == "test"


def test_read_skills_with_temp_canonical_structure(tmp_path: Path) -> None:
    """read_skills works with canonical structure in temp directory."""
    skills_file = tmp_path / "skills_matrix.csv"
    skills_file.write_text(
        "Skills,Category\nPython,Language\nDocker,DevOps\n",
        encoding="utf-8",
    )

    skills = read_skills(skills_file)
    assert "Python" in skills
    assert "Docker" in skills
    assert len(skills) == 2


def test_read_experiences_with_temp_canonical_structure(tmp_path: Path) -> None:
    """read_experiences works with canonical structure in temp directory."""
    exp_file = tmp_path / "experience_db.toml"
    exp_file.write_text(
        '[[experience]]\nid = "exp_1"\ngeneral_role_description = "Test role"\nbullet_bank = []\n',
        encoding="utf-8",
    )

    experiences = read_experiences(exp_file)
    assert len(experiences) == 1
    assert experiences[0]["id"] == "exp_1"


def test_generate_review_packet_without_sandbox_dependency(tmp_path: Path) -> None:
    """generate_review_packet CLI succeeds with canonical inputs only."""
    # Create minimal canonical structure in temp location
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

    # Verify sandbox does NOT exist
    sandbox_dir = tmp_path / "sandbox"
    assert not sandbox_dir.exists()

    # Run generate_review_packet with canonical paths only
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
