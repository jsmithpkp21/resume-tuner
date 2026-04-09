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
```

Artifacts (default):

- `data/review/outputs/baseline/latest_resume_raw.html`
- `data/review/outputs/baseline/latest_resume_raw.md`
- `data/review/outputs/baseline/latest_resume_raw_ir_snapshot.json`
- `data/review/outputs/baseline/latest_resume_raw_ir_snapshot.txt`

Processing contract:

- Default mode is `--processing-mode raw`: preserve canonical/unfiltered content.
- Use `--processing-mode processed` to apply transform/trim/enrich/rule/select stages.
- Baseline files should remain raw unless you explicitly opt into processed mode.
- Processed-mode file names use the `latest_resume_processed*` prefix.

## Headline and bottom sections

- Pass `--target-role "<job title>"` to use a dynamic headline for that application.
- `--job-url` and `--job-text-file` are mutually exclusive; pass only one.
- Education and Leadership & Community sections are sourced from `data/profile/profile.toml` and rendered at the bottom of the resume.
- If `--target-role` is not provided, role hint extraction can fall back to `--job-url` metadata (for example query/title signals).
- Company context uses deterministic research (`deterministic-v1`) for now and is saved in the generated `*_ir_snapshot.json` artifact for the selected mode (for example `latest_resume_raw_ir_snapshot.json` or `latest_resume_processed_ir_snapshot.json`); richer providers can be layered later without changing the baseline contract.
