# Experience Reconciliation Worksheet

Use this worksheet to reconcile experience data from resumes one-by-one into the canonical `data/experience/experience_db.toml`.

## Row grain

Create one row per extracted role candidate from a single source resume.

Worksheet rows are provenance records. They are used to verify source coverage and reconciliation decisions, not to constrain runtime bullet selection.

## Lifecycle intent

- Build phase: worksheet is active and required for role-by-role reconciliation.
- Steady state: canonical data in `data/experience/experience_db.toml` is the runtime source; worksheet remains as audit history.
- Retirement option: worksheet can be archived once canonical coverage is stable and replacement coverage checks exist.

## Category authority

- `data/skills/skills_matrix.csv` is the source of truth for skill-to-category mapping.
- Each skill maps to one suggested category in the skills matrix.
- `experience_db.toml` bullet `categories` are optional suggestions and may be omitted.
- Runtime generation can merge, rename, or reshuffle displayed categories per resume.
- Any bullet skill not found in `skills_matrix.csv` is a data-contract failure and must fail tests.

## Template columns

```csv
run_id,source_resume_id,source_section_label,source_role_text,source_company_text,source_dates_text,canonical_experience_id,candidate_match_ids,decision_code,conflict_codes,confidence,needs_followup,provenance_quote,selected_bullet_ids,general_role_description_seed,initial_related_skills,skill_inference_notes,notes
```

## Column definitions

- `run_id`: Processing batch marker (example: `2026-04-03-r1`).
- `source_resume_id`: Stable source file alias.
- `source_section_label`: Section header in source resume.
- `source_role_text`: Raw role title from source.
- `source_company_text`: Raw company text from source.
- `source_dates_text`: Raw date range from source.
- `canonical_experience_id`: Target `[[experience]].id`.
- `candidate_match_ids`: Pipe-separated candidate ids when matching is ambiguous.
- `decision_code`: Merge/keep/split/drop/defer decision.
- `conflict_codes`: Pipe-separated conflicts discovered during review.
- `confidence`: `C1` to `C5` confidence score.
- `needs_followup`: `yes` or `no`.
- `provenance_quote`: Short source quote proving the mapping.
- `selected_bullet_ids`: Semicolon-separated canonical bullet ids selected from `experience_db.toml`.
- `general_role_description_seed`: Factual summary seed for `general_role_description`.
- `initial_related_skills`: Semicolon-separated role-level skills from derived-plus-curated Option B.
- `skill_inference_notes`: Why inferred/curated role-level skills were included.
- `notes`: Reviewer rationale.

Source-tracking policy:

- `source_resume_id` exists to record what has been reviewed and provide traceability back to original evidence.
- Do not interpret source rows as quotas or limits on runtime bullet usage.

Review metadata policy:

- Do not auto-populate reviewer metadata in this worksheet.
- Manual review tracking happens outside this CSV during adjudication.

## Decision codes

- `K_NEW`: Keep as a new canonical experience (no valid match).
- `M_EXIST`: Merge into an existing canonical experience id.
- `M_NEW`: Merge multiple variants into a newly created canonical id.
- `SPLIT`: Source row contains multiple roles and must be split.
- `DROP_DUP`: Duplicate variant with no net-new facts.
- `DROP_OOS`: Out-of-scope section (not an experience item).
- `DEFER`: Insufficient evidence for safe merge.
- `ESCALATE`: High-risk contradiction requiring manual adjudication.

## Conflict codes

- `CT_TITLE`: Title mismatch across variants.
- `CT_COMPANY`: Company alias/entity mismatch.
- `CT_DATES`: Date range conflict.
- `CT_ORDER`: Timeline order inconsistency.
- `CT_SCOPE`: Role scope/seniority mismatch.
- `CT_CLAIM`: Impact/result claim conflict.
- `CT_TECH`: Technology stack conflict.
- `CT_LOC`: Location/work-mode conflict.
- `CT_SOURCEQ`: Low-quality or ambiguous source text.

## Confidence scale

- `C5`: Exact match, safe to write canonical.
- `C4`: High confidence with minor normalization.
- `C3`: Probable match with one non-critical ambiguity.
- `C2`: Weak match, requires corroboration.
- `C1`: Insufficient evidence.

Policy:

- Auto-accept only `C4` and `C5`.
- `C3` requires explicit note in `notes`.
- `C1` and `C2` must use `DEFER` or `ESCALATE`.

## Example rows

```csv
run_id,source_resume_id,source_section_label,source_role_text,source_company_text,source_dates_text,canonical_experience_id,candidate_match_ids,decision_code,conflict_codes,confidence,needs_followup,provenance_quote,selected_bullet_ids,general_role_description_seed,initial_related_skills,skill_inference_notes,notes
2026-04-03-r1,resume_amd_01,Professional Experience,"Senior SDET","Example Co","May 2021 - Feb 2024","exp_exampleco_senior_sdet_202105","exp_exampleco_sdet_202105","M_EXIST","CT_TITLE","C4","no","Led framework reliability and CI stabilization...","exp_exampleco_senior_sdet_202105_b12;exp_exampleco_senior_sdet_202105_b13;exp_exampleco_senior_sdet_202105_b19","Led deterministic UI/API automation reliability and CI quality gates.","Python;CI/CD;Quality gates;GitHub Actions","Derived from selected canonical bullets.","Title variant only."
2026-04-03-r1,resume_webai_02,Experience,"SDET Lead","Example Company","2021/05 to 2024/02","exp_exampleco_senior_sdet_202105","exp_exampleco_senior_sdet_202105","M_EXIST","CT_COMPANY|CT_TITLE","C4","no","Implemented release-safe quality gates in CI...","exp_exampleco_senior_sdet_202105_b13;exp_exampleco_senior_sdet_202105_b21;exp_exampleco_senior_sdet_202105_b22","Owned CI quality gates and flake reduction for distributed automation.","Python;CI/CD;Quality gates;GitHub Actions","Derived from selected canonical bullets.","Company alias normalized."
2026-04-03-r1,resume_zebra_03,Experience,"QA Automation / DevOps","Example Co","2020 - 2024","","exp_exampleco_senior_sdet_202105|exp_exampleco_qa_lead_202001","DEFER","CT_DATES|CT_SCOPE","C2","yes","Built CI/CD pipelines and automated test infra...","","","CI/CD;Automation;Test planning","Includes inferred skill candidates pending adjudication.","Date start unclear; role may combine two positions."
```

## One-at-a-time SOP

1. Load one source resume and create one worksheet row per role candidate.
2. Match against existing canonical ids.
3. Record source normalization decisions in `notes` when needed.
4. Assign `decision_code`, `conflict_codes`, and `confidence`.
5. Capture a provenance quote for each non-drop row.
6. Select canonical bullets using `selected_bullet_ids` (stable bullet ids, not counts).
7. Seed `initial_related_skills` from canonical bullet skills, then append curated role-level skills only when justified.
8. Promote only `C4` and `C5` rows into `data/experience/experience_db.toml`.
9. Enforce `DESIGN.md` rules for canonical output:
   - each experience uses `general_role_description` as summary source
   - each experience has at least 3 bullets in `bullet_bank`
   - each bullet skill exists in `data/skills/skills_matrix.csv`
10. Repeat for the next resume.
