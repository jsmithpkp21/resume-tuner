from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_resume import load_profile

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_resume.py"
PROFILE = REPO_ROOT / "data" / "profile" / "profile.toml"


def test_load_profile_reads_profile_table() -> None:
    profile = load_profile(PROFILE)
    assert profile.name
    assert profile.summary
    assert profile.education_entries
    assert profile.leadership_community_entries


def test_load_profile_rejects_blocked_path() -> None:
    blocked = REPO_ROOT / "data" / "samples" / "profile.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_profile(blocked)


def test_build_resume_cli_generates_baseline_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "baseline"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--output-dir",
            str(output_dir),
            "--target-role",
            "Staff Software Engineer",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr

    html_path = output_dir / "resume_baseline.html"
    md_path = output_dir / "resume_baseline.md"
    snapshot_path = output_dir / "resume_ir_snapshot.json"

    assert html_path.exists()
    assert md_path.exists()
    assert snapshot_path.exists()

    html_text = html_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")

    assert "Jonathan Smith" in html_text
    assert '<p class="headline">Staff Software Engineer</p>' in html_text
    assert "Architect, Python Test Framework (Video)" in html_text
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
