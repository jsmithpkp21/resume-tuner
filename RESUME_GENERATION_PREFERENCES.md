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

## Build Command Template
```bash
python scripts/build_resume.py \
  --profile data/profile/profile.toml \
  --experience-db data/experience/experience_db.toml \
  --skills-matrix data/skills/skills_matrix.csv \
  --target-role "Graphcore Senior Principal Test Framework Software Engineer" \
  --output-dir /tmp/graphcore_resume_output \
  --processing-mode processed \
  --outputs pdf,docx,html,md \
  --include-private-projects
```

`scripts/build_resume.py` is the single CLI entry point. `--outputs` selects which artifacts to emit (`pdf`, `docx`, `md`, `html` — comma-separated). Default is `pdf` (the submission-ready artifact). `scripts/export_resume_documents.py` is a deprecated back-compat shim.

**Submission-ready PDF:** `<company>_resume.pdf`. The slug comes from `--company`. When `--company` is omitted and a JD is supplied (`--job-url` or `--job-text-file`), `build_resume.py` auto-derives the slug from the JD: deterministic regex first, then LLM fallback (when `RESUME_BUILDER_LLM_ENABLED=1`). When neither a `--company` nor a derivable JD company is available, the fallback slug is `company`.
**Review HTML:** `latest_default_resume_processed.html` (left-justified, preferred for visual review).

**Important:**
- `--target-role` = INTERNAL ONLY (used for role-specific LLM optimizations)
- Professional title appears on resume via your profile headline
- Target company name is NEVER included in the output
- Profile headline reflects your actual level, may be conservative vs. target role (justify gap in cover letter)

## Notes
- `latest_resume_processed.html` = Modern (centered) template
- `latest_default_resume_processed.html` = Default (left-justified) template ← USE THIS ONE for visual review

## Output Artifacts Generated (when `--outputs=pdf,docx,html,md`)
- `<company>_resume.pdf` — **SUBMISSION ARTIFACT** (default `--outputs` produces just this)
- `<company>_resume.docx` — DOCX equivalent
- `latest_default_resume_processed.html` — left-justified review HTML
- `latest_resume_processed.html` — centered modern HTML
- `latest_resume_processed.md` — Markdown version
- `latest_resume_processed_ir_snapshot.json` — Internal representation (always emitted, for debugging)
- `latest_resume_processed_ir_snapshot.txt` — Text IR snapshot (always emitted, for debugging)

## Cover Letter Voice & Structure

The `--cover-letter` flag on `scripts/build_resume.py` (and the standalone
`scripts/build_cover_letter.py`) drafts an LLM-generated, role-and-company-
specific letter. The body requires `RESUME_BUILDER_LLM_ENABLED=1` (or
`RESUME_BUILDER_LLM_FIXTURE=1` for tests); there is no offline fallback.

### Voice
- First person, professional, direct.
- Reference the target company by name — the cover letter is the **only**
  artifact where company-specific framing belongs.
- No AI tells: never write "as an AI", "large language model", "I cannot",
  or "I'm sorry".
- Use only facts present in the inputs (profile, experience DB, JD,
  selected achievements). Do not invent metrics, team sizes, dollar
  amounts, percentages, dates, or achievements.

### Length
- Soft target: ~350 words across all paragraphs combined (`--word-budget`,
  default `350`). The pipeline warns when the rendered body exceeds the
  budget. To hard-fail when the rendered PDF spills past one page, run
  `scripts/build_cover_letter.py --enforce-page-limit` directly — the
  flag lives only on the standalone CLI. The orchestrated
  `scripts/build_resume.py --cover-letter` path always warns and never
  hard-fails on a 1-page overflow.

### Structure
- **Opening paragraph:** hook + role/company + (optional) one-sentence
  level-gap framing.
- **Body paragraphs (1–3):** specific evidence drawn from `experiences`,
  `selected_achievements`, or `independent_projects`. 3–5 sentences each.
- **Closing paragraph:** short call to action + thanks.

### Level-Gap Framing Rule
- When the candidate's profile `headline` reflects a lower level than the
  `--target-role` (e.g., Senior Staff vs. Senior Principal), include
  exactly **one** sentence in the opening or first body paragraph framing
  the transition by scope/breadth/years.
- When headlines align, omit any gap framing entirely.

### Addressee
- Pass `--hiring-manager "Name"` to address the letter explicitly.
- Otherwise, an LLM stage attempts to infer a hiring manager from the JD
  page. The inferred name must (a) clear the
  `--addressee-confidence-threshold` (default `0.85`) and (b) appear
  verbatim in the JD text. If either gate fails, the letter falls back to
  the configured `addressee_fallback`.

### Profile-Side `[cover_letter]` Table
Optional table in `data/profile/profile.toml`. Both keys are optional and
fall back to module defaults when omitted:

```toml
[cover_letter]
closing = "Sincerely,"          # default: "Sincerely,"
addressee_fallback = "Hiring Team"   # default: "Hiring Team"
```

### Output Filter
The cover-letter pipeline shares the resume's `--outputs` filter when
launched via `scripts/build_resume.py --cover-letter`. Valid tokens are
`pdf, docx, md, html`. Default emits `pdf,docx`. Run
`scripts/build_cover_letter.py` directly for finer control (custom word
budget, hiring-manager override, addressee confidence threshold, custom
filenames).

## Implementation Status (updated)
The target-role headline leakage issue is resolved in current code:
- `--target-role` is treated as an internal optimization hint
- visible headline rendering does not display target-role/company text
### Optional Future Enhancement
A dedicated `--professional-title` argument is still a possible ergonomics improvement,
but it is no longer required for the no-company-name output policy.
**See:** `CODE_FIX_PLAN_PART_B.md` for historical context and optional follow-up scope.
