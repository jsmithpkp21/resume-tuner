# Project Template

A minimal starting point for new projects that use shared tooling.
Clone this template, run the setup script, and you are ready to code.

## Starter Data Locations (resume-builder)

Use these paths as the canonical input locations for AI-driven resume generation:

- Skills matrix CSV: `data/skills/skills_matrix.csv`
- Experience database TOML: `data/experience/experience_db.toml`
- Profile metadata TOML: `data/profile/profile.toml`
- Ingestion manifest: `data/manifests/starter_data_manifest.toml`
- Sanitized resume samples: `data/samples/resumes/`
- Sanitized cover letter samples: `data/samples/cover_letters/`

Private originals (real resumes/cover letters) should stay in `sandbox/`.
This repo already ignores `sandbox/` in `.gitignore`.

See `docs/REFERENCE/DATA_LAYOUT.md` for the full layout contract.

## Baseline Resume Output (Milestone 1)

Typical one-liner usage:

```bash
make active
python scripts/build_resume.py --job-url <url>
python scripts/build_resume.py --job-url <url> --cover-letter
```

With no other flags, build_resume produces a submission-ready PDF
(processed mode) tailored to the supplied JD. When `--cover-letter` is
set, an LLM-drafted cover letter is generated alongside (PDF + DOCX by
default, honoring `--outputs`). The body requires
`RESUME_BUILDER_LLM_ENABLED=1` (or `RESUME_BUILDER_LLM_FIXTURE=1` for
tests); see [`RESUME_GENERATION_PREFERENCES.md`](RESUME_GENERATION_PREFERENCES.md)
for the cover-letter voice/structure rules and the profile-side
`[cover_letter]` table.

Output layout (auto-routed when `--output-dir` is omitted AND a
non-placeholder company slug is available — JD-derived or supplied via
`--company`; falls back to `data/outputs/baseline/` otherwise):

```
data/outputs/<company-slug>/
  resumes/
    <slug>_resume.pdf
    latest_resume_processed_ir_snapshot.json
    latest_resume_processed_ir_snapshot.txt
  cover_letters/                # only when --cover-letter is set
    <slug>_cover_letter.pdf
    <slug>_cover_letter.docx
```

The application root is the value of `--output-dir`; resume artifacts
are always written under `<output-dir>/resumes/` and cover-letter
artifacts under `<output-dir>/cover_letters/`. To pin the destination,
pass `--output-dir sandbox/outputs/resume_runs/local_review`
(`sandbox/` is git-ignored, useful for day-to-day local iteration).

Common vs Advanced flags:

- **Common (typical run):** `--job-url`, `--job-text-file`,
  `--target-role`, `--company`, `--output-dir`, `--outputs`,
  `--processing-mode`, `--cover-letter`.
- **Advanced (overrides & debug):** `--profile`, `--experience-db`,
  `--skills-matrix`, `--pdf-filename`, `--docx-filename`,
  `--allow-overflow-pdf`, `--post-layout-cleanup`,
  `--include-private-projects`, `--template`,
  `--top-skills-cap` (overrides the default top-N skill cap;
  default is 40 with LLM disabled, 46 with LLM enabled — tunable
  for visual fit, see DESIGN.md "Top-N skill cap"),
  `--fit-narrative` (`auto|on|off`, default `auto`; in auto-mode an
  LLM-judged fit score augments the profile summary with a
  fit-narrative clause when the candidate is a stretch — see DESIGN.md
  "Fit narrative").

Run `python scripts/build_resume.py --help` for the authoritative list.

Other artifacts (when `--outputs html,md` is set):

- `<root>/resumes/latest_resume_<mode>.html` (primary template)
- `<root>/resumes/latest_modern_resume_raw.html` /
  `<root>/resumes/latest_default_resume_processed.html` (secondary
  template)
- `<root>/resumes/latest_resume_<mode>.md`

Compatibility notes:

- Legacy `latest_*` artifact names remain the primary contract for
  tests/docs; only the directory layout changed.
- Company-scoped artifact aliases are no longer emitted alongside
  `latest_*`; canonical `<slug>_resume.{pdf,docx}` names cover the
  per-company case.

Export submission-ready DOCX and PDF in one run:

```bash
make active
python scripts/export_resume_documents.py --processing-mode processed --output-dir sandbox/outputs/resume_runs/submission
```

Default export artifacts (note: written under the `resumes/` subdir, same as the build_resume CLI):

- `sandbox/outputs/resume_runs/submission/resumes/company_resume.docx` (or `<company>_resume.docx` when `--company` is set)
- `sandbox/outputs/resume_runs/submission/resumes/company_resume.pdf` (or `<company>_resume.pdf` when `--company` is set)
- `sandbox/outputs/resume_runs/submission/resumes/latest_resume_processed.md` (always generated)
- `sandbox/outputs/resume_runs/submission/resumes/latest_default_resume_processed.html` (when present, preferred as the DOCX/PDF render source for better block extraction)

Export behavior notes:

- The export command always runs the Markdown pipeline first.
- DOCX/PDF rendering prefers the generated default-template HTML when available; otherwise it falls back to the processed Markdown.
- Post-layout cleanup is enabled by default during export (`--post-layout-cleanup enabled`) and may adjust the render source before DOCX/PDF generation to improve block extraction and wrap behavior.
- Use `--post-layout-cleanup disabled` when you need strict source fidelity for diffing/debugging against the unmodified processed source.
- DOCX/PDF final artifacts are written transactionally as a pair: if either phase or finalization swap fails, rollback restores prior outputs when present and removes newly-created partial outputs when no prior artifact existed.
- Trailing connector fragments emit warnings to stderr for manual review.
- PDF exports that exceed two pages fail with a non-zero exit so the submission page-limit guard is enforced.

---

## Quick Start

```bash
# 1. Clone this template (or use the GitHub "Use this template" button)
git clone https://github.com/jsmithpkp21/project-template.git my_new_project
cd my_new_project

# 2. Run setup — choose your layer (or omit for a minimal base setup)
bash scripts/setup.sh              # Default/minimal setup
bash scripts/setup.sh playwright   # With Playwright layer
bash scripts/setup.sh api          # With API layer
bash scripts/setup.sh web          # With Web layer

# 3. Follow the printed next steps (make env → make active → make setup)
```

The script handles everything:
- Downloads and runs the shared `sync_tooling.sh` to pull in all shared config
- Initializes a git repository
- Installs git hooks (branch protection)
- Applies your chosen layer
- Removes itself once complete

---

## Available Layers

| Layer        | Description                                          |
|--------------|------------------------------------------------------|
| *(none)*     | Minimal base setup — shared config only              |
| `playwright` | Adds Playwright + pytest-playwright to the layer     |
| `api`        | Placeholder for API-specific dependencies            |
| `web`        | Placeholder for web-specific dependencies            |

---

## Environment Variables

| Variable         | Default                                        | Purpose                                    |
|------------------|------------------------------------------------|--------------------------------------------|
| `TOOLING_REPO`   | `https://github.com/jsmithpkp21/tooling`      | URL of the shared tooling repository       |
| `TOOLING_VERSION`| `main`                                         | Tag or branch to sync from                 |
| `GITHUB_TOKEN`   | *(empty)*                                      | Optional token for private tooling repos   |

---

## After Setup

```bash
make env      # Create the Python virtual environment
make active   # Print the activation command
make setup    # Full setup: env + verify + hooks + pre-commit
```

The template includes minimal `VERSION`, `tooling.toml`, and
`requirements.txt` as starting points for your project; after
`scripts/setup.sh` has synced tooling, you can run `make env` /
`make setup` using these files. They are intentionally not overwritten by
`sync_tooling.sh`, so you can adjust them to your project's needs.

---

## Updating Tooling in an Existing Project

After the initial setup, use `sync_tooling.sh` to pull in updates:

```bash
bash scripts/sync_tooling.sh main .
```

---

## Related

- [tooling repo](https://github.com/jsmithpkp21/tooling) — Source of shared scripts and config
- [Application Guidance](docs/REFERENCE/APPLICATION_GUIDANCE.md) — Uncontrollables, mitigations, and pre-submit checklist
- [Pre-Submit QA Checklist](docs/REFERENCE/PRE_SUBMIT_QA_CHECKLIST.md) — Fast QA gate before each application (5 min, includes Senior SDET addendum)
- [Public Settings Runbook](docs/REFERENCE/PUBLIC_SETTINGS_RUNBOOK.md) — #99 checklist for rewrite window, GitHub settings, and public visibility flip
