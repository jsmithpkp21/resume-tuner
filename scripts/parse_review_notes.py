#!/usr/bin/env python3
"""Parse reviewer notes and extract tagged observations."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def parse_notes(csv_path: Path) -> dict[str, list[str]]:
    """Parse notes CSV and extract tagged observations by tag."""
    notes_by_tag: dict[str, list[str]] = defaultdict(list)

    try:
        with csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if not row:
                    continue
                review_item_id = (row.get("review_item_id") or "").strip()
                note = (row.get("note") or "").strip()

                # Skip comment rows
                if review_item_id.startswith("##"):
                    continue

                if not note:
                    continue

                # Extract tag if present
                tag = "general"
                if note.startswith("@"):
                    parts = note.split(":", 1)
                    if parts and parts[0].startswith("@"):
                        tag = parts[0].lstrip("@").strip()
                        if len(parts) > 1:
                            note_content = parts[1].strip()
                        else:
                            note_content = ""
                    else:
                        note_content = note
                else:
                    note_content = note

                if note_content:
                    notes_by_tag[tag].append(f"({review_item_id}) {note_content}")

    except FileNotFoundError:
        pass

    return notes_by_tag


def main() -> int:
    """Parse and display tagged notes."""
    # Find repo root by looking for data/review/reviewer_notes.csv
    script_path = Path(__file__).resolve()
    # Walk up from scripts/ -> resume-builder/
    repo_root = script_path.parent.parent
    notes_path = repo_root / "data" / "review" / "reviewer_notes.csv"

    if not notes_path.exists():
        print(f"No reviewer notes file found at {notes_path}")
        return 0

    notes_by_tag = parse_notes(notes_path)

    if not notes_by_tag:
        print("No reviewer notes captured yet.")
        return 0

    print("\n# Reviewer Notes by Tag\n")

    for tag in ["review", "general", "design"]:
        notes = notes_by_tag.get(tag, [])
        if notes:
            print(f"## @{tag}\n")
            for note in notes:
                print(f"- {note}")
            print()

    if (
        "general" in notes_by_tag
        or "review" in notes_by_tag
        or "design" in notes_by_tag
    ):
        print("---\nUse these observations when:")
        print("- @review: Update DATA_REVIEW_WORKFLOW.md or add review tooling")
        print("- @general: Next steps checklist, actionable improvements")
        print(
            "- @design: Update SKILL_CATEGORY_DETECTION_DESIGN.md or other design docs"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
