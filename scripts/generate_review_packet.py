#!/usr/bin/env python3
"""Generate non-UI review artifacts for experience/reconciliation data."""

from __future__ import annotations

import argparse
import csv
import json
import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APPROX_QUANTIFIER_RE = re.compile(
    r"\b(about|approximately|roughly|around|up to)\b|~",
    re.IGNORECASE,
)
MEASURABLE_OUTCOME_PERCENT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|x)\b", re.IGNORECASE
)
MEASURABLE_OUTCOME_VERB_PATTERN = re.compile(
    r"\b(reduced|improved|increased|decreased|cut|saved|boosted|eliminated|doubled|tripled|accelerated|scaled|grew)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Runtime blocked-input guard (#20) — shared implementation
# ---------------------------------------------------------------------------
# Use local import when run as `python scripts/generate_review_packet.py`,
# and package import when loaded as `scripts.generate_review_packet`.
if __package__ in {None, ""}:
    from _runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )
else:
    from scripts._runtime_guard import (
        assert_not_blocked_runtime_input as _assert_not_blocked_runtime_input,
    )


def _has_measurable_outcome(text: str) -> bool:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return False
    if MEASURABLE_OUTCOME_PERCENT_PATTERN.search(normalized):
        return True
    return bool(
        MEASURABLE_OUTCOME_VERB_PATTERN.search(normalized)
        and re.search(r"\b\d+(?:\.\d+)?\b", normalized)
    )


@dataclass
class Finding:
    review_item_id: str
    severity: str
    issue_type: str
    source_resume_id: str
    canonical_experience_id: str
    evidence: str
    fix_target_file: str
    fix_target_id: str
    suggested_action: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--worksheet",
        type=Path,
        default=Path("data/experience/experience_reconciliation_worksheet.csv"),
        help="Path to reconciliation worksheet CSV",
    )
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
        help="Path to skills matrix CSV",
    )
    parser.add_argument(
        "--notes",
        type=Path,
        default=Path("data/review/reviewer_notes.csv"),
        help="Persistent reviewer notes store",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/review/packets/latest"),
        help="Directory to write review packet artifacts",
    )
    return parser.parse_args()


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    _assert_not_blocked_runtime_input(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader)


def read_skills(path: Path) -> set[str]:
    skills: set[str] = set()
    for row in read_csv_rows(path):
        skill = (row.get("Skills") or "").strip()
        if skill:
            skills.add(skill)
    return skills


def read_experiences(path: Path) -> list[dict[str, Any]]:
    _assert_not_blocked_runtime_input(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    experiences = data.get("experience", [])
    if not isinstance(experiences, list):
        raise ValueError("experience_db.toml must contain [[experience]] entries")
    return experiences


def ensure_notes_store(path: Path) -> None:
    _assert_not_blocked_runtime_input(path)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "review_item_id",
                "status",
                "decision",
                "note",
                "proposed_update",
                "updated_by",
                "updated_at",
            ],
        )
        writer.writeheader()


def read_notes(path: Path) -> dict[str, dict[str, str]]:
    # Guard before any filesystem side effects (mkdir/write in ensure_notes_store).
    _assert_not_blocked_runtime_input(path)
    ensure_notes_store(path)
    notes_by_id: dict[str, dict[str, str]] = {}
    for row in read_csv_rows(path):
        review_item_id = (row.get("review_item_id") or "").strip()
        if review_item_id:
            notes_by_id[review_item_id] = row
    return notes_by_id


def _severity_for_row(row: dict[str, str]) -> str | None:
    decision_code = (row.get("decision_code") or "").strip()
    conflict_codes = (row.get("conflict_codes") or "").strip()
    confidence = (row.get("confidence") or "").strip().upper()
    needs_followup = (row.get("needs_followup") or "").strip().lower()

    if not decision_code:
        return "blocker"
    if conflict_codes:
        return "blocker"
    if needs_followup in {"yes", "true", "1"}:
        return "blocker"
    if confidence in {"C1", "C2"}:
        return "blocker"
    if confidence in {"C3", "C4"}:
        return "warning"
    return None


def worksheet_findings(
    worksheet_rows: list[dict[str, str]],
    canonical_ids: set[str],
    skills: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    for idx, row in enumerate(worksheet_rows, start=2):
        review_item_id = f"WS:{idx}"
        source_resume_id = (row.get("source_resume_id") or "").strip()
        canonical_experience_id = (row.get("canonical_experience_id") or "").strip()
        confidence = (row.get("confidence") or "").strip()
        conflict_codes = (row.get("conflict_codes") or "").strip()
        decision_code = (row.get("decision_code") or "").strip()

        if canonical_experience_id and canonical_experience_id not in canonical_ids:
            findings.append(
                Finding(
                    review_item_id=review_item_id,
                    severity="blocker",
                    issue_type="unknown_canonical_experience_id",
                    source_resume_id=source_resume_id,
                    canonical_experience_id=canonical_experience_id,
                    evidence=f"Worksheet row {idx} references unknown ID",
                    fix_target_file="data/experience/experience_reconciliation_worksheet.csv",
                    fix_target_id=review_item_id,
                    suggested_action="Set canonical_experience_id to a known role ID or mark as K_NEW candidate.",
                )
            )

        severity = _severity_for_row(row)
        if severity is not None:
            issue_type = "row_review_needed"
            if not decision_code:
                issue_type = "missing_decision_code"
            elif conflict_codes:
                issue_type = "unresolved_conflict"
            elif confidence.upper() in {"C1", "C2", "C3", "C4"}:
                issue_type = "low_confidence"

            findings.append(
                Finding(
                    review_item_id=review_item_id,
                    severity=severity,
                    issue_type=issue_type,
                    source_resume_id=source_resume_id,
                    canonical_experience_id=canonical_experience_id,
                    evidence=(
                        f"decision={decision_code or '<blank>'}; "
                        f"confidence={confidence or '<blank>'}; "
                        f"conflicts={conflict_codes or '<none>'}"
                    ),
                    fix_target_file="data/experience/experience_reconciliation_worksheet.csv",
                    fix_target_id=review_item_id,
                    suggested_action="Resolve conflicts/confidence and update worksheet decision fields.",
                )
            )

        listed_skills = [
            token.strip()
            for token in (row.get("initial_related_skills") or "").split(";")
            if token.strip()
        ]
        missing_skills = [skill for skill in listed_skills if skill not in skills]
        if missing_skills:
            findings.append(
                Finding(
                    review_item_id=review_item_id,
                    severity="warning",
                    issue_type="worksheet_skill_not_in_matrix",
                    source_resume_id=source_resume_id,
                    canonical_experience_id=canonical_experience_id,
                    evidence=f"Unknown skills: {', '.join(missing_skills)}",
                    fix_target_file="data/skills/skills_matrix.csv",
                    fix_target_id=canonical_experience_id or review_item_id,
                    suggested_action="Add true net-new skills to skills_matrix.csv or normalize worksheet skill labels.",
                )
            )

    return findings


def canonical_bullet_findings(experiences: list[dict[str, Any]]) -> list[Finding]:
    findings: list[Finding] = []
    for exp in experiences:
        exp_id = str(exp.get("id", ""))
        for bullet in exp.get("bullet_bank", []):
            bullet_id = str(bullet.get("id", ""))
            text = str(bullet.get("text", "")).strip()
            if not text:
                findings.append(
                    Finding(
                        review_item_id=f"B:{bullet_id}",
                        severity="blocker",
                        issue_type="missing_bullet_text",
                        source_resume_id="canonical",
                        canonical_experience_id=exp_id,
                        evidence="Bullet text is blank",
                        fix_target_file="data/experience/experience_db.toml",
                        fix_target_id=bullet_id,
                        suggested_action="Add canonical bullet text.",
                    )
                )
                continue

            # Flags AI-style approximate quantifiers for manual quality pass.
            if APPROX_QUANTIFIER_RE.search(text):
                findings.append(
                    Finding(
                        review_item_id=f"B:{bullet_id}",
                        severity="warning",
                        issue_type="bullet_text_manual_quality_review",
                        source_resume_id="canonical",
                        canonical_experience_id=exp_id,
                        evidence="Contains approximate quantifier wording",
                        fix_target_file="data/experience/experience_db.toml",
                        fix_target_id=bullet_id,
                        suggested_action="Review wording; tighten, expand, or de-quantify based on source evidence.",
                    )
                )
            if not _has_measurable_outcome(text):
                findings.append(
                    Finding(
                        review_item_id=f"B:{bullet_id}",
                        severity="warning",
                        issue_type="bullet_missing_measurable_outcome",
                        source_resume_id="canonical",
                        canonical_experience_id=exp_id,
                        evidence="No measurable outcome signal detected",
                        fix_target_file="data/experience/experience_db.toml",
                        fix_target_id=bullet_id,
                        suggested_action="Add action + scope + measurable result language where evidence exists.",
                    )
                )
    return findings


def coverage_snapshot(
    worksheet_rows: list[dict[str, str]], findings: list[Finding]
) -> dict[str, Any]:
    by_source = Counter(
        (row.get("source_resume_id") or "<blank>") for row in worksheet_rows
    )
    by_decision = Counter(
        (row.get("decision_code") or "<blank>") for row in worksheet_rows
    )
    by_confidence = Counter(
        (row.get("confidence") or "<blank>") for row in worksheet_rows
    )
    unresolved_conflicts = sum(
        1 for row in worksheet_rows if (row.get("conflict_codes") or "").strip()
    )
    blockers = sum(1 for f in findings if f.severity == "blocker")
    warnings = sum(1 for f in findings if f.severity == "warning")

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "worksheet_rows": len(worksheet_rows),
        "by_source_resume": dict(by_source),
        "by_decision_code": dict(by_decision),
        "by_confidence": dict(by_confidence),
        "unresolved_conflicts": unresolved_conflicts,
        "finding_counts": {"blocker": blockers, "warning": warnings},
    }


def write_findings(path: Path, findings: list[Finding]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "review_item_id",
                "severity",
                "issue_type",
                "source_resume_id",
                "canonical_experience_id",
                "evidence",
                "fix_target_file",
                "fix_target_id",
                "suggested_action",
            ],
        )
        writer.writeheader()
        for finding in findings:
            writer.writerow(finding.__dict__)


def write_fix_queue(
    path: Path,
    findings: list[Finding],
    notes_by_id: dict[str, dict[str, str]],
) -> None:
    actionable = [f for f in findings if f.severity in {"blocker", "warning"}]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "priority",
                "review_item_id",
                "issue_type",
                "fix_target_file",
                "fix_target_id",
                "suggested_action",
                "note_status",
                "note_decision",
                "note",
            ],
        )
        writer.writeheader()
        for finding in actionable:
            note = notes_by_id.get(finding.review_item_id, {})
            writer.writerow(
                {
                    "priority": "P0" if finding.severity == "blocker" else "P1",
                    "review_item_id": finding.review_item_id,
                    "issue_type": finding.issue_type,
                    "fix_target_file": finding.fix_target_file,
                    "fix_target_id": finding.fix_target_id,
                    "suggested_action": finding.suggested_action,
                    "note_status": (note.get("status") or "pending").strip(),
                    "note_decision": (note.get("decision") or "").strip(),
                    "note": (note.get("note") or "").strip(),
                }
            )


def write_notes_template(
    path: Path,
    findings: list[Finding],
    notes_by_id: dict[str, dict[str, str]],
) -> None:
    existing = set(notes_by_id)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "review_item_id",
                "status",
                "decision",
                "note",
                "proposed_update",
                "updated_by",
                "updated_at",
            ],
        )
        writer.writeheader()
        for finding in findings:
            if finding.review_item_id in existing:
                writer.writerow(notes_by_id[finding.review_item_id])
                continue
            writer.writerow(
                {
                    "review_item_id": finding.review_item_id,
                    "status": "pending",
                    "decision": "",
                    "note": "",
                    "proposed_update": "",
                    "updated_by": "",
                    "updated_at": "",
                }
            )


def write_summary(
    path: Path, snapshot: dict[str, Any], findings: list[Finding]
) -> None:
    blockers = [f for f in findings if f.severity == "blocker"]
    warnings = [f for f in findings if f.severity == "warning"]

    gate_status = "GO"
    gate_reason = "No blocking issues"
    if blockers:
        gate_status = "NO-GO"
        gate_reason = "Blocking findings present"

    top_blockers = blockers[:8]
    top_warnings = warnings[:8]

    lines = [
        "# Readiness Summary",
        "",
        f"- Gate status: **{gate_status}** ({gate_reason})",
        f"- Worksheet rows reviewed: **{snapshot['worksheet_rows']}**",
        f"- Blockers: **{len(blockers)}**",
        f"- Warnings: **{len(warnings)}**",
        f"- Unresolved conflicts: **{snapshot['unresolved_conflicts']}**",
        "",
        "## Top Blocking Findings",
        "",
    ]
    if not top_blockers:
        lines.append("- None")
    else:
        for finding in top_blockers:
            lines.append(
                f"- `{finding.review_item_id}` {finding.issue_type} -> `{finding.fix_target_file}` "
                f"({finding.evidence})"
            )

    lines.extend(["", "## Top Warning Findings", ""])
    if not top_warnings:
        lines.append("- None")
    else:
        for finding in top_warnings:
            lines.append(
                f"- `{finding.review_item_id}` {finding.issue_type} -> `{finding.fix_target_file}` "
                f"({finding.evidence})"
            )

    lines.extend(
        [
            "",
            "## Review Loop",
            "",
            "1. Open `fix_queue.csv` and process P0 items first.",
            "2. Record decisions/notes in `reviewer_notes_template.csv`.",
            "3. Apply approved edits to canonical files.",
            "4. Re-run this review generator until gate is GO.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    worksheet_rows = read_csv_rows(args.worksheet)
    experiences = read_experiences(args.experience_db)
    skills = read_skills(args.skills_matrix)
    notes_by_id = read_notes(args.notes)

    canonical_ids = {str(exp.get("id", "")) for exp in experiences}

    findings = worksheet_findings(worksheet_rows, canonical_ids, skills)
    findings.extend(canonical_bullet_findings(experiences))
    findings.sort(key=lambda f: (f.severity != "blocker", f.review_item_id))

    snapshot = coverage_snapshot(worksheet_rows, findings)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    findings_path = args.output_dir / "findings.csv"
    fix_queue_path = args.output_dir / "fix_queue.csv"
    snapshot_path = args.output_dir / "coverage_snapshot.json"
    summary_path = args.output_dir / "readiness_summary.md"
    notes_template_path = args.output_dir / "reviewer_notes_template.csv"

    write_findings(findings_path, findings)
    write_fix_queue(fix_queue_path, findings, notes_by_id)
    write_notes_template(notes_template_path, findings, notes_by_id)
    write_summary(summary_path, snapshot, findings)
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"Review packet written to: {args.output_dir}")
    print(f"- {summary_path}")
    print(f"- {findings_path}")
    print(f"- {fix_queue_path}")
    print(f"- {snapshot_path}")
    print(f"- {notes_template_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
