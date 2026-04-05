# Workflow Decisions (2026-04-03)

This record captures agreed decisions from reconciliation and pipeline planning discussions.

## Accepted decisions

1. Canonical runtime source is `data/experience/experience_db.toml` plus `data/skills/skills_matrix.csv`.
2. `data/experience/experience_reconciliation_worksheet.csv` is an audit/provenance artifact.
3. Source rows are for coverage and traceability only; they do not limit runtime bullet selection.
4. Source resume files are ingestion inputs during build-out and are not required runtime dependencies after canonical data is mature.
5. Date authority uses the first two baseline resumes (`jonsresume_master_pdf` and `amd_resume_final_docx`) when they agree.
6. Category authority remains skills-matrix-driven; bullet categories in TOML are optional suggestions.
7. Resume generation should emit a decision report showing key selection/inference choices.

## Clarifications

- No per-source quota exists for bullets.
- "Rows per source" is a reporting metric, not a selection rule.
- A/B/C option language from earlier discussion is superseded by the accepted staged architecture below.

## Staged architecture (accepted)

1. Canonical data stage
   - Maintain role entries, bullet banks, and validated skills.
2. Selection stage
   - Score and select bullets from canonical data for each target job.
3. Inference stage
   - Suggest candidate skills/category adjustments from JD + selected bullets.
4. Review stage
   - Human accepts/rejects suggestions before canonical updates.
5. Reporting stage
   - Emit an explainability report (what was selected, inferred, merged, rejected).

## Open questions

1. Worksheet end-state:
   - Keep permanently for audit, or archive after adding automated coverage checks?
2. Sample data end-state:
   - Keep minimal sanitized examples for regression prompts, or remove after generator is stable?
3. Suggestion governance:
   - Where to store accepted/declined inferred-skill decisions over time?

## Ownership notes

- Data model and reconciliation policy: repo maintainers.
- Runtime decision report schema: resume generation implementation phase.
- Coverage/retirement policy for worksheet and samples: pre-release governance task.
