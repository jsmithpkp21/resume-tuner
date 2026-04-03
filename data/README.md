# Starter Data Directory

This directory contains the canonical starter inputs that the AI pipeline reads.

## What belongs here

- `skills/skills_matrix.csv`: canonical skills matrix (single source of truth)
- `experience/experience_db.toml`: structured experience database
- `manifests/starter_data_manifest.toml`: path contract for ingestion scripts
- `samples/`: sanitized example resumes and cover letters used for layout/style reference

## Privacy boundary

- Keep private or personally identifying originals in `sandbox/`.
- Commit only sanitized examples under `data/samples/`.
