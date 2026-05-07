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
python scripts/build_resume.py --job-url "<url>"
python scripts/build_resume.py --job-url "<url>" --cover-letter
python scripts/build_resume.py --processing-mode raw
python scripts/build_resume.py --job-text-file "data/review/inputs/job_description.txt"
python scripts/build_resume.py --output-dir sandbox/outputs/resume_runs/local_review
```

Output layout — `--output-dir` is the application root; resume
artifacts are always written under `<output-dir>/resumes/`. When
`--output-dir` is omitted AND a non-placeholder company slug is
available — either auto-derived from the JD or supplied via
`--company` — build_resume routes to `data/outputs/<company-slug>/`.
With no slug, it falls back to `data/outputs/baseline/`.

Artifacts (processed mode defaults):

- `<root>/resumes/<slug>_resume.pdf` (when `--outputs` includes `pdf`, the default)
- `<root>/resumes/latest_resume_processed.html` (primary modern template; when `--outputs` includes `html`)
- `<root>/resumes/latest_default_resume_processed.html` (secondary template; when `--outputs` includes `html`)
- `<root>/resumes/latest_resume_processed.md` (when `--outputs` includes `md`)
- `<root>/resumes/latest_resume_processed_ir_snapshot.json` (always)
- `<root>/resumes/latest_resume_processed_ir_snapshot.txt` (always)

Artifacts (raw mode):

- `<root>/resumes/latest_resume_raw.html`
- `<root>/resumes/latest_modern_resume_raw.html`
- `<root>/resumes/latest_resume_raw.md`
- `<root>/resumes/latest_resume_raw_ir_snapshot.json`
- `<root>/resumes/latest_resume_raw_ir_snapshot.txt`

Cover letter (when `--cover-letter` is set):

- `<root>/cover_letters/<slug>_cover_letter.md`
  (currently a placeholder — real generator tracked in
  [issue #229](https://github.com/jsmithpkp21/resume-builder/issues/229))

Processing contract:

- Default mode is `--processing-mode processed`: submission-ready
  output. Use `--processing-mode raw` to preserve canonical/unfiltered
  content for baseline/debug runs.
- Processed-mode primary files use the `latest_resume_processed*` prefix; raw uses `latest_resume_raw*`.
- A secondary HTML artifact is always generated as `latest_<template>_resume_<mode>.html`.
- Company-scoped aliases are not emitted; output naming remains
  `<slug>_resume.{pdf,docx}` for canonical exports and `latest_*` for
  HTML/MD/snapshots.
- For local iterative runs, prefer `--output-dir sandbox/outputs/...`
  to avoid committing generated artifacts (`sandbox/` is git-ignored).

## Submission export workflow

Generate submission-ready DOCX and PDF artifacts from the same processed build output:

```bash
make active
python scripts/export_resume_documents.py --processing-mode processed --output-dir sandbox/outputs/resume_runs/submission
```

Artifacts (written under the `resumes/` subdir of `--output-dir`):

- `sandbox/outputs/resume_runs/submission/resumes/company_resume.docx` (or `<company>_resume.docx` when `--company` is set)
- `sandbox/outputs/resume_runs/submission/resumes/company_resume.pdf` (or `<company>_resume.pdf` when `--company` is set)
- `sandbox/outputs/resume_runs/submission/resumes/latest_resume_processed.md` (always generated)
- `sandbox/outputs/resume_runs/submission/resumes/latest_default_resume_processed.html` (when present, preferred as the DOCX/PDF render source)

Submission export notes:

- The export command runs the existing build pipeline once, then renders both document formats from the generated default-template HTML when available, with processed Markdown as the fallback source.
- Trailing connector fragments emit warnings to stderr for manual review.
- PDF exports that exceed two pages fail the export so the two-page submission limit is enforced.

## Headline and bottom sections

- `--target-role "<job title>"` is used for internal tailoring context only and is not rendered into visible headline/title output.
- `--job-url` and `--job-text-file` are mutually exclusive; pass only one.
- Education and Leadership & Community sections are sourced from `data/profile/profile.toml` and rendered at the bottom of the resume.
- Visible headline/title rendering uses profile headline (or safe generic fallback), never `target_role`/`role_hint` fallback.
- Company context uses deterministic research (`deterministic-v1`) for now and is saved in the generated `*_ir_snapshot.json` artifact for the selected mode (for example `latest_resume_raw_ir_snapshot.json` or `latest_resume_processed_ir_snapshot.json`); richer providers can be layered later without changing the baseline contract.
