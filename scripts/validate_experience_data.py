#!/usr/bin/env python3
"""
Validate experience_db.toml against skills_matrix.csv

Usage:
    python scripts/validate_experience_data.py
"""

import csv
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Runtime blocked-input guard (#20) — shared implementation
# ---------------------------------------------------------------------------
# Use local import when run as `python scripts/validate_experience_data.py`,
# and package import when loaded as `scripts.validate_experience_data`.
if __package__ in {None, ""}:
    from _runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )
    from measurable_outcomes import has_measurable_outcome
else:
    from scripts._runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )
    from scripts.measurable_outcomes import has_measurable_outcome


def load_experience_db(toml_path: Path) -> dict[str, Any]:
    """Load experience database from TOML file."""
    _assert_not_blocked_runtime_input(toml_path)
    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def load_skills_matrix(csv_path: Path) -> set[str]:
    """Load skills matrix from CSV file."""
    _assert_not_blocked_runtime_input(csv_path)
    skills: set[str] = set()
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Skills"):
                skills.add(row["Skills"].strip())
    return skills


def validate_experience_data(
    exp_data: dict[str, Any], valid_skills: set[str]
) -> tuple[list[str], list[str]]:
    """Validate experience data against skills matrix."""
    errors: list[str] = []
    warnings: list[str] = []

    valid_impact_types = {
        "scalability",
        "maintainability",
        "reliability",
        "mentoring",
        "delivery-speed",
        "architecture",
    }

    for exp in exp_data.get("experience", []):
        exp_id = exp.get("id", "UNKNOWN")

        # Check related_skills reference valid skills
        for skill in exp.get("related_skills", []):
            if skill not in valid_skills:
                errors.append(f"{exp_id}: related_skill '{skill}' not in skills matrix")

        # Check bullet bank
        for bullet in exp.get("bullet_bank", []):
            bullet_id = bullet.get("id", "UNKNOWN")

            # Check bullet skills
            for skill in bullet.get("skills", []):
                if skill not in valid_skills:
                    errors.append(f"{bullet_id}: skill '{skill}' not in skills matrix")

            # Check impact_type
            impact_type = bullet.get("impact_type")
            if impact_type and impact_type not in valid_impact_types:
                errors.append(f"{bullet_id}: invalid impact_type '{impact_type}'")

            # Warn if no domain
            if not bullet.get("domain"):
                warnings.append(f"{bullet_id}: missing 'domain' field")

            # Warn for weak canonical bullets that lack measurable outcome language.
            text = str(bullet.get("text") or "").strip()
            if text and not has_measurable_outcome(text):
                warnings.append(
                    f"{bullet_id}: consider adding measurable outcome language"
                )

    return errors, warnings


def main() -> int:
    """Run validation."""
    project_root = Path(__file__).parent.parent

    exp_db_path = project_root / "data" / "experience" / "experience_db.toml"
    skills_path = project_root / "data" / "skills" / "skills_matrix.csv"

    if not exp_db_path.exists():
        print(f"ERROR: {exp_db_path} not found", file=sys.stderr)
        sys.exit(1)

    if not skills_path.exists():
        print(f"ERROR: {skills_path} not found", file=sys.stderr)
        sys.exit(1)

    print("Loading experience database...")
    exp_data = load_experience_db(exp_db_path)

    print("Loading skills matrix...")
    valid_skills = load_skills_matrix(skills_path)

    print(f"Found {len(valid_skills)} valid skills")

    # Count experiences and bullets
    num_exp = len(exp_data.get("experience", []))
    num_bullets = sum(
        len(e.get("bullet_bank", [])) for e in exp_data.get("experience", [])
    )

    print(f"Found {num_exp} experiences with {num_bullets} total bullets")

    print("\nValidating...")
    errors, warnings = validate_experience_data(exp_data, valid_skills)

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for warning in warnings:
            print(f"  - {warning}")

    if not errors and not warnings:
        print("\n✅ All validations passed!")
        return 0

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
