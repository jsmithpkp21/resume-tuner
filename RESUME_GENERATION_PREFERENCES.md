# Resume Generation Preferences

## CRITICAL: Company Name Policy
- **No TARGET company names should appear on the resume**
- Graphcore (or any target company being applied to) is FOR THE COVER LETTER ONLY
- Prior employer names in professional history (for example `HP / Poly`) remain expected resume content
- The resume must stand on its own merits as a general professional document
- If generated with `--target-role` that includes a company name, REMOVE IT

## Template Preferences
- **Default Layout:** Left-justified (use `latest_default_resume_processed.html`)
- **Not:** Centered layout (the other template)

## Professional Title & Summary
- **Title should be:** "Senior Staff Software Engineer, Test Automation & Framework Architecture"
  - This is your actual Level 5 title at HP/Poly
  - No overselling — accurate to your background
- **Never:** A target role or company-specific position
- **Summary should reflect:** Your actual background (18 years, 4-country teams, 30+ releases, 16 hardware models, etc.)
- **Never:** Reference the company you're applying to

## HP/Poly Leveling Reference (for context)
- Jr. Eng
- Eng
- Senior
- Staff
- **Sr Staff (YOURS)** ← Level 5
- Principal
- Staff Principal

## Build Command Template (for Issue #120)
```bash
python scripts/build_resume.py \
  --profile data/profile/profile.toml \
  --experience-db data/experience/experience_db.toml \
  --skills-matrix data/skills/skills_matrix.csv \
  --target-role "Graphcore Senior Principal Test Framework Software Engineer" \
  --output-dir /tmp/graphcore_resume_output \
  --processing-mode processed
```

**Then use:** `latest_default_resume_processed.html` (not `latest_resume_processed.html`)

**Important:**
- `--target-role` = INTERNAL ONLY (used for role-specific LLM optimizations)
- Professional title appears on resume via your profile headline
- Target company name is NEVER included in the output
- Profile headline reflects your actual level, may be conservative vs. target role (justify gap in cover letter)

## Notes
- `latest_resume_processed.html` = Modern (centered) template
- `latest_default_resume_processed.html` = Default (left-justified) template ← USE THIS ONE

## Output Artifacts Generated
- `latest_default_resume_processed.html` — **PRIMARY** (left-justified, default layout)
- `latest_resume_processed.html` — Secondary (centered, modern layout)
- `latest_resume_processed.md` — Markdown version
- `latest_resume_processed_ir_snapshot.json` — Internal representation (for debugging)
- `latest_resume_processed_ir_snapshot.txt` — Text IR snapshot (for debugging)

## Implementation Status (updated)
The target-role headline leakage issue is resolved in current code:
- `--target-role` is treated as an internal optimization hint
- visible headline rendering does not display target-role/company text
### Optional Future Enhancement
A dedicated `--professional-title` argument is still a possible ergonomics improvement,
but it is no longer required for the no-company-name output policy.
**See:** `CODE_FIX_PLAN_PART_B.md` for historical context and optional follow-up scope.
