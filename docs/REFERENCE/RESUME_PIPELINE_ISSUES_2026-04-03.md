# Resume Pipeline Issue Backlog (2026-04-03)

Use this file to create/track GitHub issues. Each item includes concrete scope and acceptance criteria.

## EPIC: Canonical Data and Runtime Separation

### Issue 1: Enforce canonical-only runtime inputs
- Type: `feat`
- Goal: Generator consumes canonical data only (`experience_db.toml`, `skills_matrix.csv`).
- Tasks:
  1. Add loader boundaries for canonical data.
  2. Block runtime reads from `sandbox/` and `data/samples/`.
  3. Add tests proving runtime works without sample resumes.
- Acceptance criteria:
  - Runtime passes with no `data/samples/` dependency.
  - CI test fails if runtime attempts to read sample/source resumes.

### Issue 2: Worksheet lifecycle policy and coverage checks
- Type: `docs` + `test`
- Goal: Decide and enforce whether worksheet is retained or archived.
- Tasks:
  1. Define coverage check replacing manual worksheet dependence.
  2. Document archive/retention process.
  3. Add test or command that reports reviewed source coverage.
- Acceptance criteria:
  - Written policy in docs.
  - Coverage command/test available in repo.

## EPIC: Selection and Explainability

### Issue 3: Bullet selection engine from canonical role banks
- Type: `feat`
- Goal: Score/select bullets from canonical roles by job relevance.
- Tasks:
  1. Implement role and bullet relevance scoring.
  2. Implement top-N selection with layout-aware fallback.
  3. Preserve deterministic ordering for reproducibility.
- Acceptance criteria:
  - Same input produces same selected bullet ids.
  - Selection never depends on source_resume_id quotas.

### Issue 4: Decision report artifact
- Type: `feat`
- Goal: Emit a machine-readable report for each generated resume.
- Tasks:
  1. Define report schema.
  2. Include selected/rejected bullets and reasons.
  3. Include category merges/renames and inferred skills.
  4. Include JD coverage and gap summary.
- Acceptance criteria:
  - Report artifact generated with resume outputs.
  - Report includes explainability sections listed above.

## EPIC: Skill and Category Governance

### Issue 5: New-skill suggestion pipeline
- Type: `feat`
- Goal: Suggest candidate new skills from JD + selected bullets without auto-promoting.
- Tasks:
  1. Extract candidate terms from JD and selected bullet text.
  2. Match against existing skills and aliases.
  3. Output candidate additions with confidence and evidence.
- Acceptance criteria:
  - Suggestions appear in decision report.
  - No automatic mutation of canonical skill matrix.

### Issue 6: Category adjustment suggestions
- Type: `feat` + `docs`
- Goal: Suggest category merge/split/rename actions based on observed bullet clusters.
- Tasks:
  1. Detect recurring uncategorized skill clusters.
  2. Recommend category actions with evidence.
  3. Add review workflow for accepting category changes.
- Acceptance criteria:
  - Recommendations are review-only.
  - Accepted changes update docs and matrix with traceable rationale.

## EPIC: Quality and Process

### Issue 7: Date authority guardrail
- Type: `test`
- Goal: Ensure canonical dates remain anchored to approved authority policy.
- Tasks:
  1. Add policy test for authority source dates.
  2. Add clear failure message when a variant conflicts.
- Acceptance criteria:
  - Test catches canonical date drift.
  - Policy reference included in test/docs.

### Issue 8: Reconciliation consistency checks
- Type: `test`
- Goal: Validate worksheet references and confidence/conflict conventions.
- Tasks:
  1. Validate every `canonical_experience_id` and `selected_bullet_ids` reference exists.
  2. Validate allowed conflict/confidence values.
  3. Validate source coverage summary output.
- Acceptance criteria:
  - Invalid ids/codes fail CI.
  - Coverage summary produced in a reproducible command.

## Suggested implementation order

1. Issue 1
2. Issue 3
3. Issue 4
4. Issue 5
5. Issue 6
6. Issue 8
7. Issue 2
8. Issue 7

## Notes for issue creation

- Use one issue per item above.
- Link each issue to this backlog section.
- Keep PRs scoped to one issue unless explicitly grouped by an epic milestone.
