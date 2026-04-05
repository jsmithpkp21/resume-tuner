# Baseline Output Workflow

Generate a full, manually editable resume from canonical data.

## Runtime inputs

- `data/profile/profile.toml`
- `data/experience/experience_db.toml`
- `data/skills/skills_matrix.csv`

## Command

```bash
source ~/envs/resume-builder-env/bin/activate
python scripts/build_resume.py
```

Artifacts (default):

- `data/review/outputs/baseline/resume_baseline.html`
- `data/review/outputs/baseline/resume_baseline.md`
- `data/review/outputs/baseline/resume_ir_snapshot.json`
