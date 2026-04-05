from __future__ import annotations

import json
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
    assert profile.linkedin == "jonathan-j-smith-automation"
    assert profile.github == "jsmithpkp21"


def test_load_profile_normalizes_url_like_social_inputs(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.toml"
    profile_path.write_text(
        """
[profile]
name = "Test"
headline = "Engineer"
location = ""
email = ""
phone = ""
website = ""
linkedin = "https://www.linkedin.com/in/test-user/"
github = "https://github.com/test-user/"
summary = ""
""".strip()
        + "\n",
        encoding="utf-8",
    )

    profile = load_profile(profile_path)
    assert profile.linkedin == "test-user"
    assert profile.github == "test-user"


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
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert "Jonathan Smith" in html_text
    assert '<p class="headline">Staff Software Engineer</p>' in html_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in html_text
    assert "github.com/jsmithpkp21" in html_text
    assert "Architect, Python Test Framework (Video)" in html_text
    assert "<h2>Education</h2>" in html_text
    assert "<h2>Leadership &amp; Community</h2>" in html_text
    assert "## Education" in md_text
    assert "## Leadership & Community" in md_text
    assert "linkedin.com/in/jonathan-j-smith-automation" in md_text
    assert "github.com/jsmithpkp21" in md_text
    assert snapshot["profile"]["linkedin"] == "jonathan-j-smith-automation"
    assert (
        snapshot["profile"]["linkedin_url"]
        == "linkedin.com/in/jonathan-j-smith-automation"
    )
    assert snapshot["profile"]["github"] == "jsmithpkp21"
    assert snapshot["profile"]["github_url"] == "github.com/jsmithpkp21"
