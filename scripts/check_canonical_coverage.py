#!/usr/bin/env python3
"""Worksheet-independent canonical coverage check for issue #21.

Reads only the canonical files (``data/experience/experience_db.toml`` and
``data/skills/skills_matrix.csv``) and reports coverage signals that survive
worksheet archive. Hard gates mirror the invariants ``DESIGN.md`` describes
and ``scripts/validate_experience_data.py`` already enforces (GRD present,
>=3 bullets, every bullet skill in matrix, every ``related_skills`` entry in
matrix); soft signals are informational distributions.

Run with ``--strict`` for CI use::

    python3 scripts/check_canonical_coverage.py --strict
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Runtime blocked-input guard (#20) — shared implementation.
# ---------------------------------------------------------------------------
if __package__ in {None, ""}:
    from _runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )
else:
    from scripts._runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )

MIN_BULLETS_PER_ROLE = 3


@dataclass
class HardGateFailure:
    gate: str
    experience_id: str
    detail: str


@dataclass
class CoverageReport:
    generated_at: str
    inputs: dict[str, str]
    experience_count: int
    bullet_count: int
    bullets_per_role: dict[str, Any]
    skills_matrix_size: int
    skills_referenced: int
    skills_unreferenced: int
    roles_missing_related_skills: list[str]
    hard_gate_failures: list[HardGateFailure] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "inputs": self.inputs,
            "experience_count": self.experience_count,
            "bullet_count": self.bullet_count,
            "bullets_per_role": self.bullets_per_role,
            "skills_matrix_size": self.skills_matrix_size,
            "skills_referenced": self.skills_referenced,
            "skills_unreferenced": self.skills_unreferenced,
            "roles_missing_related_skills": self.roles_missing_related_skills,
            "hard_gate_failures": [f.__dict__ for f in self.hard_gate_failures],
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experience-db",
        type=Path,
        default=Path("data/experience/experience_db.toml"),
        help="Path to canonical experience TOML",
    )
    parser.add_argument(
        "--skills-matrix",
        type=Path,
        default=Path("data/skills/skills_matrix.csv"),
        help="Path to canonical skills matrix CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/review/coverage_report.json"),
        help="Path to write coverage report JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any hard gate fails (intended for CI)",
    )
    return parser.parse_args(argv)


def load_experience_db(path: Path) -> list[dict[str, Any]]:
    _assert_not_blocked_runtime_input(path)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    experiences = data.get("experience", [])
    if not isinstance(experiences, list):
        raise ValueError(
            f"Expected [[experience]] array in {path}, got {type(experiences).__name__}"
        )
    return experiences


def load_skills_matrix(path: Path) -> set[str]:
    _assert_not_blocked_runtime_input(path)
    skills: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            skill = (row.get("Skills") or "").strip()
            if skill:
                skills.add(skill)
    return skills


def evaluate_hard_gates(
    experiences: list[dict[str, Any]], skills: set[str]
) -> list[HardGateFailure]:
    failures: list[HardGateFailure] = []
    for exp in experiences:
        exp_id = str(exp.get("id") or "<missing-id>")

        grd = (exp.get("general_role_description") or "").strip()
        if not grd:
            failures.append(
                HardGateFailure(
                    gate="missing_general_role_description",
                    experience_id=exp_id,
                    detail="general_role_description is empty or missing",
                )
            )

        bullets = exp.get("bullet_bank") or []
        if len(bullets) < MIN_BULLETS_PER_ROLE:
            failures.append(
                HardGateFailure(
                    gate="bullet_bank_below_minimum",
                    experience_id=exp_id,
                    detail=f"bullet_bank has {len(bullets)} entries, minimum is {MIN_BULLETS_PER_ROLE}",
                )
            )

        for bullet in bullets:
            bullet_id = str(bullet.get("id") or "<missing-bullet-id>")
            for skill in bullet.get("skills", []) or []:
                if skill not in skills:
                    failures.append(
                        HardGateFailure(
                            gate="bullet_skill_not_in_matrix",
                            experience_id=exp_id,
                            detail=f"bullet {bullet_id!r} references skill {skill!r} not in skills_matrix.csv",
                        )
                    )

        # Mirror validate_experience_data.py: related_skills must also be in the matrix.
        # related_skills_inferred is intentionally informational only, matching that script.
        for skill in exp.get("related_skills", []) or []:
            if skill not in skills:
                failures.append(
                    HardGateFailure(
                        gate="related_skill_not_in_matrix",
                        experience_id=exp_id,
                        detail=f"related_skill {skill!r} not in skills_matrix.csv",
                    )
                )
    return failures


def summarize_bullets_per_role(experiences: list[dict[str, Any]]) -> dict[str, Any]:
    counts = [len(exp.get("bullet_bank") or []) for exp in experiences]
    if not counts:
        return {"min": 0, "max": 0, "median": 0, "mean": 0.0, "histogram": {}}
    histogram = Counter(counts)
    return {
        "min": min(counts),
        "max": max(counts),
        "median": statistics.median(counts),
        "mean": round(statistics.fmean(counts), 2),
        "histogram": {str(k): histogram[k] for k in sorted(histogram)},
    }


def summarize_skill_usage(
    experiences: list[dict[str, Any]], skills: set[str]
) -> tuple[int, int]:
    """Count matrix skills referenced anywhere in canonical data.

    Includes bullet skills, ``related_skills``, and ``related_skills_inferred``
    so utilization metrics reflect real matrix usage — e.g. ``ADB`` appears in
    ``related_skills`` while bullets use ``Android UI automation (ADB)``.
    """
    referenced: set[str] = set()
    for exp in experiences:
        for skill in exp.get("related_skills", []) or []:
            if skill in skills:
                referenced.add(skill)
        for skill in exp.get("related_skills_inferred", []) or []:
            if skill in skills:
                referenced.add(skill)
        for bullet in exp.get("bullet_bank") or []:
            for skill in bullet.get("skills", []) or []:
                if skill in skills:
                    referenced.add(skill)
    return len(referenced), len(skills - referenced)


def roles_missing_related_skills(experiences: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for exp in experiences:
        related = exp.get("related_skills") or []
        if not related:
            missing.append(str(exp.get("id") or "<missing-id>"))
    return missing


def build_report(
    experience_db_path: Path,
    skills_matrix_path: Path,
) -> CoverageReport:
    experiences = load_experience_db(experience_db_path)
    skills = load_skills_matrix(skills_matrix_path)

    bullet_count = sum(len(exp.get("bullet_bank") or []) for exp in experiences)
    referenced, unreferenced = summarize_skill_usage(experiences, skills)

    return CoverageReport(
        generated_at=datetime.now(UTC).isoformat(),
        inputs={
            "experience_db": str(experience_db_path),
            "skills_matrix": str(skills_matrix_path),
        },
        experience_count=len(experiences),
        bullet_count=bullet_count,
        bullets_per_role=summarize_bullets_per_role(experiences),
        skills_matrix_size=len(skills),
        skills_referenced=referenced,
        skills_unreferenced=unreferenced,
        roles_missing_related_skills=roles_missing_related_skills(experiences),
        hard_gate_failures=evaluate_hard_gates(experiences, skills),
    )


def write_report(report: CoverageReport, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def render_summary(report: CoverageReport) -> str:
    lines: list[str] = []
    lines.append("Canonical coverage report")
    lines.append("=" * 30)
    lines.append(f"Generated:        {report.generated_at}")
    lines.append(f"Experiences:      {report.experience_count}")
    lines.append(f"Bullets total:    {report.bullet_count}")
    bpr = report.bullets_per_role
    lines.append(
        f"Bullets per role: min={bpr['min']} median={bpr['median']} max={bpr['max']} mean={bpr['mean']}"
    )
    lines.append(
        f"Skills matrix:    {report.skills_matrix_size} entries "
        f"({report.skills_referenced} referenced, {report.skills_unreferenced} unreferenced)"
    )
    lines.append(
        f"Roles missing related_skills: {len(report.roles_missing_related_skills)}"
    )
    lines.append("")
    if report.hard_gate_failures:
        lines.append(f"❌ Hard gate failures: {len(report.hard_gate_failures)}")
        for failure in report.hard_gate_failures:
            lines.append(
                f"  - [{failure.gate}] {failure.experience_id}: {failure.detail}"
            )
    else:
        lines.append("✅ All hard gates passed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args.experience_db, args.skills_matrix)
    write_report(report, args.output)
    print(render_summary(report))
    if args.strict and report.hard_gate_failures:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
