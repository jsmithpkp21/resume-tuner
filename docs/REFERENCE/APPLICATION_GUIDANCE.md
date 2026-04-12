# Application Guidance: Uncontrollables, Mitigations, and Pre-Submit Checklist
> Relates to: [Issue #61](https://github.com/jsmithpkp21/resume-builder/issues/61)
> Parent tracker: [Issue #56](https://github.com/jsmithpkp21/resume-builder/issues/56)
---
## Uncontrollables
These factors exist in every hiring pipeline and cannot be directly changed.
Accepting them removes wasted effort and keeps the focus on what you can improve.
| Factor | Why it is out of your control |
|--------|-------------------------------|
| **Recruiter interpretation** | A recruiter may screen on title keywords, years-of-experience formulas, or stack-match rules before a hiring manager sees the resume. |
| **ATS parsing behavior** | Applicant tracking systems differ in how they tokenize job titles, parse skills, and score keyword density. A well-crafted resume can still score poorly on a specific ATS. |
| **Company leveling and budget** | A role may be budget-frozen at a level below your target, or leveled with criteria (for example direct-report count) that do not reflect the technical depth you offer. |
| **Pipeline timing** | A req may close or be put on hold after you apply, regardless of fit. |
| **Hiring manager preferences** | Individual interviewers weight different signals — breadth vs. depth, framework familiarity, domain overlap — in ways that vary role by role. |
---
## Mitigations
These are concrete actions to reduce the impact of the uncontrollables above.
### Resume tailoring
- **Top-third rule**: The first two-thirds of the resume (visible above the fold in most ATS
  views) should be tightly aligned to the JD's most-repeated signals — role title, domain
  keywords, and two or three core responsibilities.
- **Role title alignment**: Use the `--target-role` flag (or set a target role in the JD text
  file) so the processed resume headline and summary mirror the JD's exact title wording.
- **Skills section ordering**: Run `--processing-mode processed` to activate role-aware skill
  selection (`select_skills` stage). Category ordering follows relevance score rather than
  alphabetical order.
### Intent and framing
- **Senior SDET scope clarifier**: When the target role says "Senior SDET" or "QA Lead",
  prepend a one-sentence intent line in your cover note (see template below) to flag
  hands-on design and delivery — not just execution.
- **Avoid implied authority inflation**: Bullets should describe scope of influence, not
  line-management authority, unless you held direct reports. The `experience_db.toml` bullet
  guidelines enforce this via `scope_note` categories.
### Cover note
Keep the cover note to three sentences maximum:
1. Role and company with a specific reason for interest (not generic enthusiasm).
2. One concrete match between your background and a stated JD requirement.
3. Intent clarifier for scope if the JD mixes IC and management signals.
**Senior SDET intent clarifier template:**
> Applying as a hands-on Senior SDET — my interest is in framework design, CI reliability,
> and embedded test architecture, not a management track.
---
## Pre-Submit Checklist
Apply this checklist before submitting each application.
Every item should be verifiable against the generated resume artifact.
- [ ] Target role title in resume header matches the JD title exactly (or closest equivalent).
- [ ] Profile summary references the role label from `--target-role` — not a generic fallback.
- [ ] Top-third bullets (first two or three bullets under the most recent role) address the
  top-priority requirements from the JD.
- [ ] Skills section shows categories relevant to the JD at the top (run
  `--processing-mode processed` to activate role-aware ordering).
- [ ] No bullets imply direct-report authority unless that is true and relevant.
- [ ] Cover note is three sentences or fewer and includes one specific JD requirement match.
- [ ] If the JD mixes IC and management signals, the cover note includes the Senior SDET scope
  clarifier.
- [ ] Output artifact was generated against the latest `data/experience/experience_db.toml`
  (no stale sandbox file).
- [ ] Processed artifact verified: open `latest_resume_processed.html` and confirm the summary
  reads cleanly without truncation or fragment sentences.
---
## Quick Command Reference
```bash
# Generate a tailored processed resume for a specific role
python scripts/build_resume.py \
  --target-role "Senior SDET" \
  --processing-mode processed \
  --output-dir sandbox/outputs/latest_application
# Generate with a job description text file for keyword alignment
python scripts/build_resume.py \
  --job-text-file sandbox/jd_target.txt \
  --processing-mode processed \
  --output-dir sandbox/outputs/latest_application
```
See `docs/REFERENCE/DATA_LAYOUT.md` for data file locations.
