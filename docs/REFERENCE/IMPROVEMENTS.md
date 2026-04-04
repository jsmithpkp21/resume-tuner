# Improvements Backlog

This document tracks improvement ideas and links them to design documents, decision records, and GitHub issues.

## Current State

### Core Governance Documents

- **Decision record**: `docs/REFERENCE/WORKFLOW_DECISIONS_2026-04-03.md` — Accepted decisions on data model, runtime separation, and staged architecture.
- **Actionable issue backlog**: `docs/REFERENCE/RESUME_PIPELINE_ISSUES_2026-04-03.md` — 8 prioritized GitHub issues spanning canonical data, selection, governance, and quality.

### Active Design Areas

#### Skill and Category Detection (2026-04-03)

**Design**: `docs/REFERENCE/SKILL_CATEGORY_DETECTION_DESIGN.md`

This design covers the skill/category suggestion system:

- **Issue 5** (Feat): New-skill suggestion pipeline
  - Extract candidate skills from JD + selected bullets.
  - Score by frequency, confidence, and evidence.
  - Output to decision report without auto-promoting.

- **Issue 6** (Feat + Docs): Category adjustment suggestions
  - Analyze bullet clustering within categories.
  - Recommend merge/split/rename actions.
  - Support review-only workflow for governance.

Both issues operate in a non-invasive, review-only mode with traceable rationale for accepted suggestions.

**Status**: Design complete; ready for GitHub issue creation and implementation planning.

**Related decisions**:
- Suggestion governance question in WORKFLOW_DECISIONS_2026-04-03.md
- Staged architecture (decision record, section "Staged architecture (accepted)").

#### Data Review Packet Workflow (2026-04-03)

**Workflow doc**: `docs/REFERENCE/DATA_REVIEW_WORKFLOW.md`

This adds a no-UI review loop for canonical/resolution data:

- Generates a compact review packet (`readiness_summary.md`, `findings.csv`, `fix_queue.csv`, `coverage_snapshot.json`).
- Supports incremental review so we can fix high-confidence entries first.
- Uses persistent notes store at `data/review/reviewer_notes.csv` to capture reviewer decisions and proposed text updates.

**Status**: Implementation added; ready for iterative reviewer notes and canonical edits.

**Related issues**:
- `Issue #27` (reconciliation consistency checks)
- `Issue #24` and `Issue #25` (skill/category review pipeline integration)


#### Selection Engine and Audience-Aware Framing (2026-04-04)
**Design**: `docs/REFERENCE/SELECTION_ENGINE_DESIGN.md`
This design covers the audience-aware selection layer that enables generating a "Staff Software
Engineer" resume from experience accumulated under different titles:
- **Issue 28** (Feat): Add `role_audience` tag to bullet schema
  - Per-bullet field: `architect` / `lead` / `generalist`.
  - Encodes which framing best fits each bullet without hardcoded engine logic.
  - Includes CI validation for field presence and controlled vocabulary.
- **Issue 29** (Feat): JD parsing module
  - Extract seniority level, role type, required/preferred skills, and domain signals from raw JD text.
  - Output a structured `jd_profile.yaml` artifact that drives all downstream scoring.
  - Forward unmatched JD terms to the new-skill suggestion pipeline (Issue 24 / #24).
- **Issue 30** (Feat): Title and description framing
  - Map canonical job titles to audience-appropriate target-facing titles via `config/title_map.toml`.
  - Generate 1–2 line role summaries per experience entry from canonical description + selected bullets + JD profile.
  - All framing is a generated output artifact; canonical data is never mutated.
All three issues feed into the existing bullet selection engine (#22) and decision report (#23).
**Status**: Design complete; ready for GitHub issue creation and implementation.
**Related decisions**:
- Staged architecture in `WORKFLOW_DECISIONS_2026-04-03.md` (selection stage, inference stage).
- `DESIGN.md` Section 4 (Relevance Engine) and Section 8 (Summary Generation Rules).
- `SKILL_CATEGORY_DETECTION_DESIGN.md` (Issues 5–6 / #24–#25 receive JD parser output).
## Maintenance Notes

- Keep this file non-empty because it is synced as a managed documentation artifact.
- Add new design areas as entries (with date, design doc link, and related issue numbers).
- Move completed issues to GitHub milestone or changelog as needed.
- When creating GitHub issues from backlog items, update this file with issue links (e.g., `Issue #123`).
