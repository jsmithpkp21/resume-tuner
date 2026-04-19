# Data Review Workflow (No UI)

This workflow produces a review packet you can scan quickly and annotate without opening raw CSV rows directly.

## Why this exists

- Canonical data quality must be reviewable without a custom UI.
- We need a repeatable way to capture your notes and apply fixes incrementally.
- We can review only the "looks good" items first and keep unresolved items queued.

## Inputs

- `data/experience/experience_reconciliation_worksheet.csv`
- `data/experience/experience_db.toml`
- `data/skills/skills_matrix.csv`
- `data/review/reviewer_notes.csv` (persistent notes store)

## Outputs

Running the generator creates:

- `readiness_summary.md` (go/no-go + top issues)
- `findings.csv` (all findings)
- `fix_queue.csv` (prioritized actionable queue)
- `coverage_snapshot.json` (metrics snapshot)
- `reviewer_notes_template.csv` (current queue seeded for notes)

## Review process

1. Run the packet generator.
2. Read `readiness_summary.md` for gate status.
3. Work from `fix_queue.csv` (`P0` first, then `P1`).
4. Add your decisions in `reviewer_notes_template.csv`.
5. Copy approved notes into `data/review/reviewer_notes.csv`.
6. Apply approved edits to canonical files.
7. Re-run generator and validations.

## Notes schema

`data/review/reviewer_notes.csv` columns:

- `review_item_id`: stable ID from findings (`WS:<row>` or `B:<bullet_id>`)
- `status`: `pending | accepted | rejected | needs_followup`
- `decision`: short decision label (`keep`, `rewrite`, `remove`, etc.)
- `note`: rationale + optional tags (see below)
- `proposed_update`: optional replacement text
- `updated_by`: reviewer name/initials
- `updated_at`: ISO timestamp

When `decision` is `will_not_fix`, store reason codes in `note` as semicolon-delimited tokens,
for example: `source-lacks-quant; downstream-impact-unknown`.
`fix_queue.csv` surfaces these in `note_reason_codes`.

### Tagged notes

Start your note with a tag to categorize observations:

- **`@review`**: Improvements to review process itself, tooling ideas, workflow refinements
- **`@general`**: General next steps, observations, actionable improvements outside review loop
- **`@design`**: Additions/clarifications for design docs (e.g., SKILL_CATEGORY_DETECTION_DESIGN.md)

**Example notes:**

```
WS:13,accepted,keep,"@general: AMD authority confirmed. Add date authority precedence table to WORKFLOW_DECISIONS.md","","jonathan","2026-04-03T20:30Z"
WS:18,pending,needs_followup,"@review: This CT_DATES conflict would be caught earlier if we had date range overlap check in validator","","jonathan","2026-04-03T20:32Z"
B:exp_hp_poly_architect_python_video_202306_b01,accepted,rewrite,"@design: Add evidence-tagging pattern to Issue 4 (decision report) - bullets should include 'source: jonsresume_master_pdf' tag","Transformed an inherited ADB/UI Automator-based system into a lightweight abstraction layer supporting embedded UI testing across PolyOS, Zoom, Teams, and Google Meet (source: master resume).","jonathan","2026-04-03T20:35Z"
```

### Extract and view tagged notes

Run the notes parser anytime to see what you've captured by tag:

```bash
python scripts/parse_review_notes.py
```

Output groups observations by `@review`, `@general`, `@design` for easy export to docs/issues.

## Commands

```bash
cd ~/projects/resume-builder
python scripts/generate_review_packet.py
python scripts/validate_experience_data.py
pytest -q tests/scripts/test_experience_skill_category_contract.py
```

## Policy

- Keep canonical runtime sources authoritative.
- Keep worksheet as audit/provenance.
- Use notes store for human decisions so review history remains diffable.

## Additional warning semantics

- `bullet_skill_text_mismatch` is warning-only and checks a small set of explicit tooling
  skills (`CI/CD`, `GitHub Actions`, `Docker`) against bullet text.
- Resolve by either adding explicit text evidence for the skill or removing the mismatched skill.
