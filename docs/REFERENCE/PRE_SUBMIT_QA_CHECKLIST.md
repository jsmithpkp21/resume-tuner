# Pre-Submit Resume QA Checklist
> Issue: [#63](https://github.com/jsmithpkp21/resume-builder/issues/63)
> Related: [Application Guidance](APPLICATION_GUIDANCE.md) for strategy context.
Run this checklist against the generated artifact before submitting each application.
Target time: 5 minutes or less.
---
## 1. Generate the artifact
```bash
python scripts/build_resume.py \
  --target-role "Senior SDET" \
  --processing-mode processed \
  --output-dir data/review/outputs/latest_application
```
Open `data/review/outputs/latest_application/latest_resume_processed.html` in a browser
and `latest_resume_processed.md` in a text editor. All checks below apply to that output.
---
## 2. Profile summary
- [ ] Summary is present and not the raw profile default (check for a role-targeted opening
  phrase, not a generic fallback such as "Software engineer specializing in Software Engineer").
- [ ] Summary is two sentences or fewer and reads cleanly without trailing fragments
  (does not end with `to.`, `focused.`, or similar clipped phrases).
- [ ] Role label in summary matches the `--target-role` value used for generation.
---
## 3. Bullet quality
- [ ] No bullet ends with a dangling connector or fragment word
  (for example `to.`, `and.`, `in.`, `for the.`).
- [ ] No two bullets in the same role start with the same action word.
- [ ] No skill term appears identically in adjacent bullets within the same role section.
---
## 4. Ownership and authority wording
- [ ] No bullet claims direct-report authority (for example "managed a team of") unless
  that is literally true for that role.
- [ ] Bullets describe scope of influence, not line management (for example "led adoption of"
  rather than "managed engineers").
- [ ] No bullet states company-wide business impact for work that was team or project scope.
---
## 5. JD keyword coverage
- [ ] The target role title appears in the resume header (generated from `--target-role`).
- [ ] At least two of the JD'''s top three repeated technical terms appear in the top-third
  of the resume (header, summary, or first-role bullets).
- [ ] Skills section includes at least one skill from each major requirement area in the JD.
---
## 6. Skills section
- [ ] Skills section is present and non-empty.
- [ ] No skill term appears in multiple categories in the same rendered output.
- [ ] Categories are in relevance order for the target role, not alphabetical order
  (processed mode activates role-aware category ranking).
---
## 7. Contact and metadata
- [ ] Name, location, and email are present and correct.
- [ ] LinkedIn URL resolves (format is `linkedin.com/in/<slug>`).
- [ ] GitHub URL resolves (format is `github.com/<username>`).
- [ ] Phone number is present if desired for the application channel.
- [ ] Date ranges on all roles are filled in with no placeholder text.
---
## 8. Layout sanity
- [ ] Both role title and company appear on each experience entry.
- [ ] No experience entry has zero bullets.
- [ ] Education section is present.
- [ ] No section heading is duplicated.
---
## Senior SDET addendum
Apply these additional checks when the target role is Senior SDET, QA Lead, or similar.
- [ ] Summary does not imply management track (no "managed", "led a team", "director").
- [ ] At least one bullet references test framework design or CI integration, not just
  test execution.
- [ ] Cover note (if included) contains the scope clarifier:
  > Applying as a hands-on Senior SDET - my interest is in framework design, CI reliability,
  > and embedded test architecture, not a management track.
- [ ] No bullet uses "oversaw testing" without describing the hands-on technical contribution.
---
## Quick reference: common defects
| Defect | Where to look | Fix |
|--------|---------------|-----|
| Fragment summary ending in `to.` or `in.` | Profile summary | Regenerate with `--processing-mode processed` |
| Duplicate action word in same role | First word of each bullet | Edit `experience_db.toml` bullet text |
| Alphabetical skill categories | Skills section order | Confirm `--processing-mode processed` was used |
| Generic role fallback in summary | Summary first line | Pass `--target-role` explicitly |
| Ownership inflation | Bullets with "managed" or "oversaw" | Edit `experience_db.toml` bullet scope |
| Missing contact field | Header contact line | Update `data/profile/profile.toml` |
