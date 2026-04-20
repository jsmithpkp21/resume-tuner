# Baseline Output Workflow

Generate a full, manually editable resume from canonical data.

## Runtime inputs

- `data/profile/profile.toml`
- `data/experience/experience_db.toml`
- `data/skills/skills_matrix.csv`
- Optional: `--job-url "<job posting url>"` (LinkedIn, Indeed, or company site)
- Optional: `--job-text-file "<path to plain-text JD>"` (offline/login-walled fallback)

## Command

```bash
make active
python scripts/build_resume.py
python scripts/build_resume.py --processing-mode raw
python scripts/build_resume.py --processing-mode processed
python scripts/build_resume.py --job-url "https://www.linkedin.com/jobs/search-results/?currentJobId=4380299765&keywords=SDET"
python scripts/build_resume.py --job-text-file "data/review/inputs/job_description.txt"
python scripts/build_resume.py --output-dir sandbox/outputs/resume_runs/local_review
```

Artifacts (raw mode defaults):

- `data/review/outputs/baseline/latest_resume_raw.html`
- `data/review/outputs/baseline/latest_modern_resume_raw.html`
- `data/review/outputs/baseline/latest_resume_raw.md`
- `data/review/outputs/baseline/latest_resume_raw_ir_snapshot.json`
- `data/review/outputs/baseline/latest_resume_raw_ir_snapshot.txt`

Artifacts (processed mode defaults):

- `data/review/outputs/baseline/latest_resume_processed.html` (primary modern template)
- `data/review/outputs/baseline/latest_default_resume_processed.html` (secondary template)
- `data/review/outputs/baseline/latest_resume_processed.md`
- `data/review/outputs/baseline/latest_resume_processed_ir_snapshot.json`
- `data/review/outputs/baseline/latest_resume_processed_ir_snapshot.txt`

Processing contract:

- Default mode is `--processing-mode raw`: preserve canonical/unfiltered content.
- Use `--processing-mode processed` to apply transform/trim/enrich/rule/select stages.
- Baseline files should remain raw unless you explicitly opt into processed mode.
- Processed-mode primary files use the `latest_resume_processed*` prefix.
- A secondary HTML artifact is always generated as `latest_<template>_resume_<mode>.html`.
- Company-scoped aliases are not emitted; output naming remains company-agnostic (`latest_*`).
- For local iterative runs, prefer `--output-dir sandbox/outputs/...` to avoid committing generated artifacts.

## Headline and bottom sections

- `--target-role "<job title>"` is used for internal tailoring context only and is not rendered into visible headline/title output.
- `--job-url` and `--job-text-file` are mutually exclusive; pass only one.
- Education and Leadership & Community sections are sourced from `data/profile/profile.toml` and rendered at the bottom of the resume.
- Visible headline/title rendering uses profile headline (or safe generic fallback), never `target_role`/`role_hint` fallback.
- Company context uses deterministic research (`deterministic-v1`) for now and is saved in the generated `*_ir_snapshot.json` artifact for the selected mode (for example `latest_resume_raw_ir_snapshot.json` or `latest_resume_processed_ir_snapshot.json`); richer providers can be layered later without changing the baseline contract.
