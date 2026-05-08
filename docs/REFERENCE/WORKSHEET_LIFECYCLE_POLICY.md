# Worksheet Lifecycle Policy

Policy for the lifecycle of `data/experience/experience_reconciliation_worksheet.csv` and the canonical coverage signals that replace it once it is archived.

Implements the `docs` half of issue #21. The companion script `scripts/check_canonical_coverage.py` (run with `--strict` for CI use) implements the worksheet-independent coverage check.

## States

The worksheet moves through three explicit states.

### 1. Build (current)

- Worksheet is **active and required** for role-by-role reconciliation.
- One row per extracted role candidate (or per delta-reconciled canonical change) per source resume.
- `scripts/generate_review_packet.py` reads the worksheet to produce findings, fix queue, and worksheet-derived coverage snapshot.
- Promotion of `C4`/`C5` rows into `data/experience/experience_db.toml` happens here.

### 2. Steady-state

Reached when canonical coverage is stable enough that the worksheet adds no new signal that the canonical files do not already encode. The worksheet is kept in-tree as audit history but is no longer a required input for adding net-new evidence.

Entry criteria — **all must hold simultaneously**, verified by `python3 scripts/check_canonical_coverage.py --strict` plus the worksheet-shape checks below:

Canonical (checked by `scripts/check_canonical_coverage.py`, hard gates):

- Every `[[experience]]` has a non-empty `general_role_description`.
- Every `[[experience]]` has at least 3 entries in `bullet_bank` (matches `DESIGN.md`).
- Every bullet skill in `experience_db.toml` exists in `data/skills/skills_matrix.csv`.

Worksheet (checked by `scripts/generate_review_packet.py` coverage snapshot):

- Zero rows with `decision_code` in `{DEFER, ESCALATE}`.
- Zero rows with `confidence` in `{C1, C2}`.
- Zero rows with non-empty `conflict_codes` (i.e. `unresolved_conflicts == 0`).
- Every non-drop row (`decision_code` not in `{DROP_DUP, DROP_OOS}`) has a non-empty `canonical_experience_id` and `provenance_quote`.

Holding the canonical coverage check and the worksheet-shape checks together is intentional: the canonical gates prove the runtime data is sound, and the worksheet gates prove that no in-flight reconciliation work is being abandoned by the archive.

### 3. Archived

The worksheet has been retired. Canonical files are the only authoritative source.

Entry from steady-state requires an explicit, dated, reviewer-attributed decision (see archive procedure below).

## Archive procedure

To move from steady-state to archived:

1. Confirm steady-state criteria above. `python3 scripts/check_canonical_coverage.py --strict` must exit 0. The review-packet coverage snapshot must show zero unresolved conflicts and zero `C1`/`C2`/`DEFER`/`ESCALATE` rows.
2. Move the worksheet to a dated archive path:

   ```bash
   mkdir -p data/experience/archive
   git mv data/experience/experience_reconciliation_worksheet.csv \
          data/experience/archive/experience_reconciliation_worksheet_$(date -u +%Y-%m-%d).csv
   ```

3. Write `data/experience/lifecycle_state.json` with the snapshot of why archival was approved:

   ```json
   {
     "state": "archived",
     "archived_at": "2026-05-07T00:00:00Z",
     "archived_by": "<reviewer initials or handle>",
     "archived_worksheet_path": "data/experience/archive/experience_reconciliation_worksheet_2026-05-07.csv",
     "criteria_met": {
       "canonical_coverage_strict": true,
       "unresolved_conflicts": 0,
       "low_confidence_rows": 0,
       "deferred_or_escalated_rows": 0
     },
     "notes": "<short rationale + link to PR or decision record>"
   }
   ```

4. Update `scripts/generate_review_packet.py` to skip worksheet inputs when `lifecycle_state.json` reports `state == "archived"`. (Out of scope for the policy PR; tracked as the follow-up below.)
5. Open a PR titled `chore(experience): archive reconciliation worksheet` referencing this policy and issue #21. The PR description must include the canonical-coverage report and the review-packet coverage snapshot at archive time.

The dated archive path and the `lifecycle_state.json` snapshot together form a permanent audit record: anyone reading the repo months later can see when archive happened, who approved it, and what the data looked like at that moment.

## Un-archive procedure

If new source resumes need reconciliation after archive (e.g., a previously unknown employer surfaces), restore the worksheet rather than starting a new file so prior provenance is not orphaned:

1. `git mv` the dated archive CSV back to `data/experience/experience_reconciliation_worksheet.csv`.
2. Update `lifecycle_state.json` to `state: "build"` and add an `unarchived_at` / `unarchived_by` / `reason` block. Keep the original `archived_at` / `archived_by` for history.
3. Re-run `python3 scripts/check_canonical_coverage.py --strict` and the review packet generator to confirm the restored worksheet integrates cleanly.
4. Open a PR titled `chore(experience): unarchive reconciliation worksheet` linking the new evidence and the rationale.

## What replaces the worksheet after archive

The two coverage signals that survive archive:

- **Canonical coverage** — `python3 scripts/check_canonical_coverage.py --strict`. Reads `experience_db.toml` and `skills_matrix.csv` only, with no worksheet dependence. Hard-gates on the same rules `scripts/validate_experience_data.py` enforces (GRD present, ≥3 bullets, bullet skills in matrix, `related_skills` in matrix). Soft signals on bullets-per-role distribution and skill-matrix utilization across bullet skills, `related_skills`, and `related_skills_inferred`.
- **Audit trail** — the dated CSV under `data/experience/archive/` and `lifecycle_state.json`. Read-only after archive; never edited in place.

The worksheet-derived snapshot in `scripts/generate_review_packet.py` is **not** retained after archive. Once `lifecycle_state.json` is `archived`, the review-packet generator no longer needs worksheet inputs to function.

## Scope and follow-ups

This policy defines states, criteria, and procedures. It does **not**:

- Archive the existing 64-row worksheet now. Archive is a separate, reviewer-driven decision with its own PR.
- Wire the canonical coverage check into `make check`. `Makefile` is a tooling-managed (synced) file, so a `coverage-report` make target is held until either the upstream tooling Makefile gains a `Makefile.local` include hook or the script is invoked directly from a tooling-side target. For now, run `python3 scripts/check_canonical_coverage.py --strict` directly.
- Modify `scripts/generate_review_packet.py` to read `lifecycle_state.json`. That belongs in the archive PR, not this one.

Tracked separately:

- Follow-up: skip-worksheet-on-archive support in `generate_review_packet.py`.
- Follow-up: tooling issue to add `-include Makefile.local` (or equivalent) to the upstream tooling Makefile, then add a `coverage-report` make target locally without breaking sync drift; once that is in place, opt the target into `make check`.

## Related

- Design invariants: `DESIGN.md`.
- Worksheet schema and column definitions: `docs/REFERENCE/EXPERIENCE_RECONCILIATION_WORKSHEET.md`.
- Review workflow: `docs/REFERENCE/DATA_REVIEW_WORKFLOW.md`.
- Backlog: `docs/REFERENCE/RESUME_PIPELINE_ISSUES_2026-04-03.md` (Issue 2).
- Decision record: `docs/REFERENCE/WORKFLOW_DECISIONS_2026-04-03.md`.
- Issue: #21.
