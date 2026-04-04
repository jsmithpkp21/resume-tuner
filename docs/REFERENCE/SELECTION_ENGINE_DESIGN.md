# Selection Engine Design (2026-04-04)
## Overview
This design document covers the audience-aware selection layer for the resume builder pipeline:
- **`role_audience` tag schema extension** — per-bullet framing signal (architect / lead / generalist)
- **JD parsing module** — structured extraction of seniority, role-type, and skill signals from job descriptions
- **Bullet selection engine** — audience-aware scoring and selection from canonical bullet banks
- **Title and description framing** — mapping canonical job titles to target-role language
These components together allow the system to produce a "Staff Software Engineer" resume from experience
that was accumulated under titles such as "Lead Framework Designer" — by selecting bullets and framing
descriptions that match what hiring managers at a given seniority level expect to read.
## Design Principles
1. **Audience awareness is data, not code**: the `role_audience` tag lives on each bullet so the
   engine can filter without hardcoded rules.
2. **Framing is a selection output, not a mutation**: canonical job titles and `general_role_description`
   are never changed; the target-facing title and summary are generated artifacts.
3. **JD drives everything**: seniority level, role type, and required skills are extracted from
   the JD and drive all scoring decisions.
4. **Reproducible**: same canonical data + same JD produces the same selected bullets and same framing.
5. **Review-only inference**: JD-derived suggestions (new skills, category adjustments) do not
   auto-mutate canonical data.
---
## Component 1: role_audience Tag Schema Extension
### Purpose
Each bullet in experience_db.toml describes work from a specific lens. A bullet about evaluating
migration paths reads differently to an architect audience than a lead audience. The role_audience
tag encodes which framing the bullet supports best.
### Schema Addition
Add an optional role_audience field to each [[experience.bullet_bank]] entry:
```toml
[[experience.bullet_bank]]
id = "exp_hp_poly_lead_technical_designer_corp_automation_201506_b01"
text = "Evaluated migration paths for unifying automation across Video, Audio, and Network organizations."
skills = ["Architecture", "Automation Strategy"]
categories = ["Architecture", "Automation & Frameworks"]
impact_type = "architecture"
domain = "corporate-platform"
role_audience = "architect"   # NEW FIELD
```
### Allowed Values
| Value        | Meaning                                                                                     |
|--------------|---------------------------------------------------------------------------------------------|
| architect    | Best fit for architect, principal, or staff-IC roles; emphasizes system design and scope    |
| lead         | Best fit for tech lead or senior IC roles; emphasizes team, delivery, and ownership         |
| generalist   | Applicable across audiences; includes both framing signals                                  |
All three values are valid in the selection engine. A bullet with role_audience = "generalist"
is always eligible regardless of target role type. A bullet with role_audience = "architect" is
scored higher when the target role signals architect/staff/principal expectations.
### Tagging Guidelines
- A bullet that emphasizes scope, cross-org influence, system design, or strategic evaluation -> architect
- A bullet that emphasizes team leadership, code review, delivery, or mentoring -> lead
- A bullet that contains both, or is neutral (tooling, CI, framework features) -> generalist
### Validation
A CI test should enforce:
- Every bullet has a role_audience field once tagging is complete.
- Allowed values match the controlled vocabulary above.
### Related Issue
- **Issue 28**: Add role_audience tag to experience_db.toml bullet schema (new)
---
## Component 2: JD Parsing Module
### Purpose
The selection engine needs a structured representation of the target job to drive scoring.
The JD parser extracts:
1. Seniority level (Staff, Senior, Lead, Principal, etc.)
2. Role type (IC-architect, IC-lead, manager, generalist)
3. Required skills (explicitly stated or strongly implied)
4. Preferred skills ("nice to have" signals)
5. Domain signals (video, cloud, embedded, web, etc.)
6. Impact signals (scale, reliability, delivery speed, mentoring, etc.)
### Architecture
```
Input: Raw Job Description (text/URL)
  -> Text Normalizer (strip HTML, normalize case)
  -> Section Extractor (Requirements, Preferred, About role)
  -> Signal Extractor
       - Seniority: "staff", "principal", "lead", etc.
       - Role type: "architect", "manager", "IC"
       - Skills: match against skills_matrix.csv
       - Domain: detect video/cloud/embedded context
  -> JD Profile (structured YAML output)
```
### JD Profile Schema
```yaml
# jd_profile.yaml (example)
seniority_level: "staff"        # staff | senior | lead | principal | manager | not_detected
role_type: "architect"          # architect | lead | generalist | manager
required_skills:
  - "Python"
  - "CI/CD"
  - "distributed systems"
preferred_skills:
  - "Kubernetes"
  - "Terraform"
domain_signals:
  - "cloud"
  - "platform engineering"
impact_signals:
  - "reliability"
  - "scalability"
  - "cross-team influence"
```
### Acceptance Criteria
- JD profile artifact generated from raw JD text input.
- Seniority level correctly extracted from at least 5 representative JDs.
- Skills matched against skills_matrix.csv with confidence scores.
- Unmatched terms forwarded as new-skill candidates (feeds Issue 24).
### Related Issues
- **Issue 29**: JD parsing module (new)
- **Issue 22** (#22): Bullet selection engine (downstream consumer of JD profile)
- **Issue 24** (#24): New-skill suggestion pipeline (receives unmatched JD terms)
---
## Component 3: Audience-Aware Bullet Selection Engine
This extends the existing bullet selection engine (Issue 22 / #22) with audience-aware scoring.
### Composite Scoring Model
```
score(bullet, jd_profile) =
    skill_overlap_score      * weight_skill
  + impact_alignment_score   * weight_impact
  + domain_alignment_score   * weight_domain
  + audience_alignment_score * weight_audience
  + recency_score            * weight_recency
```
### Audience Alignment Score
```
if jd_profile.role_type == bullet.role_audience:    -> 1.0
elif bullet.role_audience == "generalist":          -> 0.75
else (mismatch):                                    -> 0.4  (penalized, not excluded)
```
### Selection Rules
1. Select top-N bullets per role weighted by composite score.
2. Prefer bullets where role_audience matches jd_profile.role_type.
3. Always include at least 3 bullets per role (fallback to lower-scoring if needed).
4. Preserve deterministic order: same inputs produce same output.
### Related Issues
- **Issue 22** (#22): Bullet selection engine (extend to use role_audience and JD profile)
---
## Component 4: Title and Description Framing
### Purpose
A hiring manager reading for "Staff Software Engineer" does not know what "Lead Technical Designer,
Corporate Automation Initiative" means. This component maps canonical job titles and role descriptions
to target-role language without altering canonical data.
### Title Mapping Config (config/title_map.toml)
```toml
[[title_map]]
canonical = "Lead Framework Designer, Video SQA Automation"
audience_map = [
  { role_type = "architect", output = "Staff Software Engineer - Test Infrastructure" },
  { role_type = "lead",      output = "Senior Software Engineer - Framework Lead" },
  { role_type = "generalist", output = "Lead Software Engineer - Test Automation" },
]
[[title_map]]
canonical = "Lead Technical Designer, Corporate Automation Initiative"
audience_map = [
  { role_type = "architect", output = "Staff Engineer - Automation Platform" },
  { role_type = "lead",      output = "Senior Engineer - Automation Strategy" },
  { role_type = "generalist", output = "Lead Engineer - Test Automation" },
]
```
### Role Summary Generation Rules
1. Start from general_role_description as the semantic anchor.
2. Incorporate highest-scoring selected bullets as context.
3. Reframe language toward JD seniority signals:
   - Staff/architect: scope, cross-org, platform ownership
   - Lead: delivery, team, quality
4. Output: 1-2 line summary as the first line under each job on the resume.
5. Summary is a generated artifact; never written back to canonical data.
### Acceptance Criteria
- config/title_map.toml loaded and applied per target role type.
- Role summary generated for each experience entry using canonical description + selected bullets + JD profile.
- Generated titles and summaries captured in decision report artifact (#23).
- Canonical job_title and general_role_description remain unchanged in experience_db.toml.
### Related Issues
- **Issue 30**: Title and description framing config and generator (new)
- **Issue 23** (#23): Decision report artifact (captures generated titles and summaries)
- **Issue 22** (#22): Bullet selection engine (provides selected bullets to summary generator)
---
## End-to-End Flow (Updated)
```
Job Description (raw text)
        |
        v
JD Parsing Module (Issue 29)
        |  jd_profile.yaml
        v
Bullet Selection Engine (Issue 22, extended via Issue 28 tags)
        |  selected_bullets[]
        v
Title & Description Framing (Issue 30)
        |  target_title, role_summary per experience
        v
Decision Report (Issue 23 / #23)
        |  selected bullets, rejected bullets, inferred skills,
        |  target titles, role summaries, JD coverage gaps
        v
Layout & Output Generator (Issues 14, 16 / #14, #16)
```
---
## New Issues Required
### Issue 28: Add role_audience tag to experience_db.toml bullet schema
- **Type**: feat
- **Goal**: Add role_audience field to every [[experience.bullet_bank]] entry.
- **Tasks**:
  1. Define schema: allowed values architect, lead, generalist.
  2. Tag all existing bullets in experience_db.toml.
  3. Add CI validation test for field presence and value constraints.
  4. Update schema documentation.
- **Acceptance criteria**:
  - All bullets have a role_audience field.
  - CI test rejects bullets with missing or invalid role_audience.
- **Relates to**: #22, #12
### Issue 29: JD parsing module
- **Type**: feat
- **Goal**: Parse raw job description text into a structured JD profile YAML.
- **Tasks**:
  1. Implement text normalizer and section extractor.
  2. Implement seniority level and role type detection.
  3. Implement skill term extraction and matching against skills_matrix.csv.
  4. Output structured jd_profile.yaml artifact.
  5. Forward unmatched terms to new-skill suggestion pipeline (Issue 24 / #24).
- **Acceptance criteria**:
  - JD profile produced from raw JD text input.
  - Seniority level correctly extracted for representative test cases.
  - Matched skills linked to skills_matrix.csv entries.
  - Unmatched terms forwarded as new-skill candidates.
- **Relates to**: #22, #24, #23
### Issue 30: Title and description framing
- **Type**: feat
- **Goal**: Map canonical job titles to audience-appropriate target-facing titles and generate
  role summaries per experience entry.
- **Tasks**:
  1. Define config/title_map.toml format and load logic.
  2. Implement title mapper using JD profile role type.
  3. Implement role summary generator using canonical description + selected bullets + JD profile.
  4. Emit generated titles and summaries to decision report.
  5. Ensure canonical data is never mutated.
- **Acceptance criteria**:
  - Target-facing title generated per experience entry per target role.
  - Role summary generated per experience entry.
  - Both captured in decision report artifact.
  - experience_db.toml unchanged after generation run.
- **Relates to**: #22, #23
---
## Dependency Map
| Issue | Depends On                                          |
|-------|-----------------------------------------------------|
| 28    | None (data tagging, standalone)                     |
| 29    | skills_matrix.csv (for skill matching)              |
| 30    | Issue 22 (selected bullets), Issue 29 (JD profile)  |
| 22    | Issue 28 (role_audience tags), Issue 29 (JD profile)|
| 23    | Issues 22, 29, 30 (aggregates all outputs)          |
## Suggested Implementation Order
1. Issue 28 -- tag existing bullets (data-only, immediate value)
2. Issue 29 -- JD parsing (foundation for scoring)
3. Issue 22 -- extend selection engine with audience scoring (depends on 28 + 29)
4. Issue 30 -- title/description framing (depends on 22 + 29)
5. Issue 23 -- decision report captures outputs of 22, 29, 30
---
## Related Decision Records
- docs/REFERENCE/WORKFLOW_DECISIONS_2026-04-03.md -- Staged architecture, canonical runtime
  sources, and suggestion governance.
- docs/REFERENCE/RESUME_PIPELINE_ISSUES_2026-04-03.md -- Full upstream issue backlog (Issues 1-8
  / GitHub #20-#27).
- docs/REFERENCE/SKILL_CATEGORY_DETECTION_DESIGN.md -- Skill/category suggestion system
  (Issues 5-6 / GitHub #24-#25).
- DESIGN.md -- Top-level system design spec (relevance engine, layout engine, summary generation).
