# Data Layout for AI Starter Inputs

This document defines where resume-builder stores starter datasets and reference files.

## Canonical starter inputs

- Skills matrix CSV: `data/skills/skills_matrix.csv`
- Experience database TOML: `data/experience/experience_db.toml`
- Profile metadata TOML: `data/profile/profile.toml`
- Ingestion path contract: `data/manifests/starter_data_manifest.toml`

## Sample documents for style/layout seeding

- Resume samples: `data/samples/resumes/`
- Cover letter samples: `data/samples/cover_letters/`

Use only sanitized, commit-safe files in `data/samples/`.

`data/samples/` is transitional for style and prompt-seeding work. Production runtime should not require sample files once canonical data is complete.

## Private originals

Keep private source documents in `sandbox/`.

Recommended local subfolders:

- `sandbox/resumes/`
- `sandbox/cover_letters/`

This repository ignores `sandbox/` via `.gitignore`, so originals can be used locally without committing them.

## Design alignment

This layout aligns with `DESIGN.md`:

- Skills Matrix is the canonical source for skills/category routing.
- Experience DB provides structured role metadata and bullet banks.
- Profile metadata provides the baseline resume header/contact shell.
- Reconciliation worksheet provides provenance/coverage evidence and review history.
- Sample resumes/cover letters provide optional formatting/language references.
