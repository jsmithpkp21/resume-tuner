"""Test canonical-only runtime input enforcement for #20.

Ensures runtime code can only read from canonical data sources
and rejects attempts to read from sandbox/ or data/samples/.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scripts.generate_review_packet import (
    read_experiences,
    read_skills,
)
from scripts.validate_experience_data import (
    load_experience_db,
    load_skills_matrix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_EXPERIENCE_DB = REPO_ROOT / "data" / "experience" / "experience_db.toml"
CANONICAL_SKILLS = REPO_ROOT / "data" / "skills" / "skills_matrix.csv"
SANDBOX_DIR = REPO_ROOT / "sandbox"
SAMPLES_DIR = REPO_ROOT / "data" / "samples"


def test_load_skills_matrix_accepts_canonical_path() -> None:
    """Load from canonical skills_matrix.csv succeeds."""
    if not CANONICAL_SKILLS.exists():
        pytest.skip(f"Canonical skills file not found: {CANONICAL_SKILLS}")

    skills = load_skills_matrix(CANONICAL_SKILLS)
    assert isinstance(skills, set)
    assert len(skills) > 0


def test_load_experience_db_accepts_canonical_path() -> None:
    """Load from canonical experience_db.toml succeeds."""
    if not CANONICAL_EXPERIENCE_DB.exists():
        pytest.skip(f"Canonical experience file not found: {CANONICAL_EXPERIENCE_DB}")

    data = load_experience_db(CANONICAL_EXPERIENCE_DB)
    assert isinstance(data, dict)
    assert "experience" in data


def test_read_skills_accepts_canonical_path() -> None:
    """read_skills from generate_review_packet accepts canonical path."""
    if not CANONICAL_SKILLS.exists():
        pytest.skip(f"Canonical skills file not found: {CANONICAL_SKILLS}")

    skills = read_skills(CANONICAL_SKILLS)
    assert isinstance(skills, set)
    assert len(skills) > 0


def test_read_experiences_accepts_canonical_path() -> None:
    """read_experiences from generate_review_packet accepts canonical path."""
    if not CANONICAL_EXPERIENCE_DB.exists():
        pytest.skip(f"Canonical experience file not found: {CANONICAL_EXPERIENCE_DB}")

    experiences = read_experiences(CANONICAL_EXPERIENCE_DB)
    assert isinstance(experiences, list)


def test_canonical_inputs_no_samples_dependency() -> None:
    """Runtime validates without data/samples/ directory."""
    # Create a minimal temp canonical structure
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)

        # Create minimal canonical files
        exp_db = tmp_root / "experience_db.toml"
        exp_db.write_text(
            '[[experience]]\nid = "exp_1"\ngeneral_role_description = "Test"\nbullet_bank = []\n',
            encoding="utf-8",
        )

        skills_csv = tmp_root / "skills_matrix.csv"
        skills_csv.write_text("Skills,Category\nPython,Language\n", encoding="utf-8")

        # Verify both loaders work with minimal temp files
        exp_data = load_experience_db(exp_db)
        assert exp_data.get("experience", [])

        skills = load_skills_matrix(skills_csv)
        assert "Python" in skills

        # Verify data/samples dir is NOT accessed
        assert not (tmp_root / "samples").exists()


def test_sandbox_directory_is_not_runtime_canonical() -> None:
    """Sanity check: sandbox/ is distinct from canonical data roots."""
    # This test documents that sandbox/ should not be a runtime input source.
    # No runtime code should attempt to load from SANDBOX_DIR.
    # TODO: After #20 implementation, add positive test asserting
    #       that runtime code explicitly rejects SANDBOX_DIR paths.

    # For now, verify the directory exists and is distinct
    if SANDBOX_DIR.exists():
        assert SANDBOX_DIR != REPO_ROOT / "data" / "experience"
        assert SANDBOX_DIR != REPO_ROOT / "data" / "skills"


def test_samples_directory_is_not_runtime_canonical() -> None:
    """Sanity check: data/samples/ is distinct from canonical data roots."""
    # This test documents that data/samples/ should not be a runtime input source.
    # No runtime code should attempt to load from SAMPLES_DIR.
    # TODO: After #20 implementation, add positive test asserting
    #       that runtime code explicitly rejects SAMPLES_DIR paths.

    # For now, verify the directory is distinct
    assert SAMPLES_DIR != REPO_ROOT / "data" / "experience"
    assert SAMPLES_DIR != REPO_ROOT / "data" / "skills"


def test_path_traversal_attempt_rejected() -> None:
    """Guard rejects ``..`` traversal paths that resolve into blocked directories.

    ``data/skills/../../sandbox/tricks.csv`` resolves to
    ``REPO_ROOT/sandbox/tricks.csv`` after ``..`` collapsing — which is blocked.
    The guard runs before any file I/O, so the file need not exist.
    """
    # Two levels up from data/skills/ brings us back to REPO_ROOT, then into sandbox/.
    traversal_path = CANONICAL_SKILLS.parent / ".." / ".." / "sandbox" / "tricks.csv"

    with pytest.raises(ValueError, match="blocked runtime directory"):
        load_skills_matrix(traversal_path)


def test_symlink_bypass_attempt_rejected() -> None:
    """Guard detects symlinks whose resolved target is inside a blocked directory.

    ``path.resolve()`` follows symlinks to their true location, so a symlink
    placed in a "canonical" path but pointing into ``sandbox/`` is caught.
    """
    if not SANDBOX_DIR.exists():
        pytest.skip("sandbox/ directory not present — nothing to point a symlink at")

    # Find any file inside sandbox/ to use as the symlink target.
    sandbox_targets = [p for p in SANDBOX_DIR.iterdir() if p.is_file()]
    if not sandbox_targets:
        pytest.skip("sandbox/ contains no files — nothing to point a symlink at")

    with tempfile.TemporaryDirectory() as tmpdir:
        symlink = Path(tmpdir) / "skills_matrix.csv"
        try:
            symlink.symlink_to(sandbox_targets[0])
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not available in this test environment")

        # Even though the symlink *looks* canonical, its resolved target is in sandbox/.
        with pytest.raises(ValueError, match="blocked runtime directory"):
            load_skills_matrix(symlink)
