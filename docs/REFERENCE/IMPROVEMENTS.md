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

## Maintenance Notes

- Keep this file non-empty because it is synced as a managed documentation artifact.
- Add new design areas as entries (with date, design doc link, and related issue numbers).
- Move completed issues to GitHub milestone or changelog as needed.
- When creating GitHub issues from backlog items, update this file with issue links (e.g., `Issue #123`).
