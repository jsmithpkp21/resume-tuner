"""Test runtime blocked-input policy for #20.
Runtime loaders must reject paths that resolve into blocked roots
(`sandbox/` and `data/samples/`) while allowing non-blocked inputs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.generate_review_packet import read_experiences, read_skills
from scripts.validate_experience_data import load_experience_db, load_skills_matrix

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_EXPERIENCE_DB = REPO_ROOT / "data" / "experience" / "experience_db.toml"
CANONICAL_SKILLS = REPO_ROOT / "data" / "skills" / "skills_matrix.csv"
SANDBOX_DIR = REPO_ROOT / "sandbox"
SAMPLES_DIR = REPO_ROOT / "data" / "samples"


def test_load_skills_matrix_accepts_repo_skills_path() -> None:
    """`load_skills_matrix` accepts the repo skills file path."""
    if not CANONICAL_SKILLS.exists():
        pytest.skip(f"Repo skills file not found: {CANONICAL_SKILLS}")
    skills = load_skills_matrix(CANONICAL_SKILLS)
    assert isinstance(skills, set)
    assert len(skills) > 0


def test_load_experience_db_accepts_repo_experience_path() -> None:
    """`load_experience_db` accepts the repo experience DB path."""
    if not CANONICAL_EXPERIENCE_DB.exists():
        pytest.skip(f"Repo experience file not found: {CANONICAL_EXPERIENCE_DB}")
    data = load_experience_db(CANONICAL_EXPERIENCE_DB)
    assert isinstance(data, dict)
    assert "experience" in data


def test_read_skills_accepts_repo_skills_path() -> None:
    """`read_skills` accepts the repo skills path."""
    if not CANONICAL_SKILLS.exists():
        pytest.skip(f"Repo skills file not found: {CANONICAL_SKILLS}")
    skills = read_skills(CANONICAL_SKILLS)
    assert isinstance(skills, set)
    assert len(skills) > 0


def test_read_experiences_accepts_repo_experience_path() -> None:
    """`read_experiences` accepts the repo experience DB path."""
    if not CANONICAL_EXPERIENCE_DB.exists():
        pytest.skip(f"Repo experience file not found: {CANONICAL_EXPERIENCE_DB}")
    experiences = read_experiences(CANONICAL_EXPERIENCE_DB)
    assert isinstance(experiences, list)


def test_loaders_accept_arbitrary_non_blocked_temp_paths() -> None:
    """Loaders accept non-blocked temp paths (blocklist policy, not allowlist)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        exp_db = tmp_root / "experience_db.toml"
        exp_db.write_text(
            '[[experience]]\nid = "exp_1"\ngeneral_role_description = "Test"\nbullet_bank = []\n',
            encoding="utf-8",
        )
        skills_csv = tmp_root / "skills_matrix.csv"
        skills_csv.write_text("Skills,Category\nPython,Language\n", encoding="utf-8")
        exp_data = load_experience_db(exp_db)
        assert exp_data.get("experience", [])
        skills = load_skills_matrix(skills_csv)
        assert "Python" in skills


def test_sandbox_directory_is_rejected_by_guard() -> None:
    """Guard rejects direct runtime reads rooted in `sandbox/`."""
    blocked_path = SANDBOX_DIR / "skills_matrix.csv"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_skills_matrix(blocked_path)


def test_samples_directory_is_rejected_by_guard() -> None:
    """Guard rejects direct runtime reads rooted in `data/samples/`."""
    blocked_path = SAMPLES_DIR / "skills_matrix.csv"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_skills_matrix(blocked_path)


def test_load_experience_db_rejects_sandbox_path() -> None:
    """Guard rejects `load_experience_db` calls rooted in `sandbox/`."""
    blocked_path = SANDBOX_DIR / "experience_db.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_experience_db(blocked_path)


def test_load_experience_db_rejects_samples_path() -> None:
    """Guard rejects `load_experience_db` calls rooted in `data/samples/`."""
    blocked_path = SAMPLES_DIR / "experience_db.toml"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_experience_db(blocked_path)


def test_path_traversal_attempt_rejected() -> None:
    """Guard rejects `..` traversal that resolves into a blocked directory."""
    traversal_path = CANONICAL_SKILLS.parent / ".." / ".." / "sandbox" / "tricks.csv"
    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_skills_matrix(traversal_path)


def test_symlink_bypass_attempt_rejected() -> None:
    """Guard rejects symlink inputs whose resolved target is in `sandbox/`."""
    # Create a real file inside sandbox/ so the test never skips because the
    # directory is absent or empty.  Clean up the file (and the dir if we
    # created it) in the finally block so the repo stays clean.
    sandbox_created = not SANDBOX_DIR.exists()
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    target_file = SANDBOX_DIR / "_symlink_test_target.csv"
    target_file.write_text("Skills,Category\nPython,Language\n", encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            symlink = Path(tmpdir) / "skills_matrix.csv"
            try:
                symlink.symlink_to(target_file)
            except (OSError, NotImplementedError):
                pytest.skip("Symlinks not available in this test environment")
            with pytest.raises(ValueError, match="blocked runtime directory"):
                load_skills_matrix(symlink)
    finally:
        target_file.unlink(missing_ok=True)
        if sandbox_created:
            try:
                SANDBOX_DIR.rmdir()
            except OSError:
                pass  # non-empty is fine; leave it
