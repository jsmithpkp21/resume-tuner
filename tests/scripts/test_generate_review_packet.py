from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

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
