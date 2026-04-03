# Data Layout for AI Starter Inputs

This document defines where resume-builder stores starter datasets and reference files.

## Canonical starter inputs

- Skills matrix CSV: `data/skills/skills_matrix.csv`
- Experience database TOML: `data/experience/experience_db.toml`
- Ingestion path contract: `data/manifests/starter_data_manifest.toml`

## Sample documents for style/layout seeding

- Resume samples: `data/samples/resumes/`
- Cover letter samples: `data/samples/cover_letters/`

Use only sanitized, commit-safe files in `data/samples/`.

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
- Sample resumes/cover letters provide formatting and language references.
