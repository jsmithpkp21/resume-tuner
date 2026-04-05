# Starter Data Directory

This directory contains the canonical starter inputs that the AI pipeline reads.

## What belongs here

- `skills/skills_matrix.csv`: canonical skills matrix (single source of truth)
- `experience/experience_db.toml`: structured canonical experience database (role metadata, bullet bank, role-level related skills)
- `profile/profile.toml`: baseline resume profile data (name/contact/summary plus education and leadership/community sections)
- `experience/experience_reconciliation_worksheet.csv`: pointer-based worksheet for one-by-one resume reconciliation (maps source rows to canonical role and bullet ids)
- `manifests/starter_data_manifest.toml`: path contract for ingestion scripts
- `samples/`: sanitized example resumes and cover letters used for layout/style reference during build-out (transitional, not required runtime input)

## Category policy

- `skills_matrix.csv` is the authority for skill-to-category mapping (one suggested category per skill).
- `experience_db.toml` stores bullet `skills`; bullet `categories` are optional suggestions only.
- Resume generation may rename, merge, or reshuffle displayed categories dynamically based on job relevance and layout constraints.

## Privacy boundary

- Keep private or personally identifying originals in `sandbox/`.
- Commit only sanitized examples under `data/samples/`.

## Runtime dependency policy

- Runtime generation depends on canonical data (`skills_matrix.csv` and `experience_db.toml`), not on sample resumes.
- Baseline output generation additionally reads `profile/profile.toml` for presentation metadata.
- `experience_reconciliation_worksheet.csv` is retained for audit/provenance and coverage tracking.

## Baseline output command

```bash
source ~/envs/resume-builder-env/bin/activate
python scripts/build_resume.py
```
