# Skill and Category Detection Design (2026-04-03)

## Overview

This design document details the skill/category detection and suggestion system, covering:
- **New-skill suggestion pipeline** (Issue 5)
- **Category adjustment suggestions** (Issue 6)

Both features operate in a review-only mode: they generate recommendations without auto-mutating canonical data.

## Design Principles

1. **Non-invasive**: Suggestions appear in the decision report; no automatic canonical updates.
2. **Evidence-driven**: Every suggestion includes source (JD terms, selected bullets) and confidence metrics.
3. **Traceable**: Accepted suggestions record rationale and reviewer notes in canonical updates.
4. **Incremental**: Suggestions improve as more resumes are processed and reviewed.

## Issue 5: New-Skill Suggestion Pipeline

### Goal
Extract candidate new skills from job descriptions and selected resume bullets, recommend additions to `skills_matrix.csv` without auto-promotion.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Job Description (JD) + Selected Resume Bullets              │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────▼────────────┐
        │ Term Extraction         │
        │ (Tokenize, normalize)   │
        └────────────┬────────────┘
                     │
        ┌────────────▼────────────────────────┐
        │ Candidate Skill Identification      │
        │ (Filter stopwords, apply heuristics)│
        └────────────┬───────────────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │ Existing Skill Matching               │
        │ (Exact + fuzzy match vs. matrix)      │
        └────────────┬──────────────────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │ Candidate Skill Ranking               │
        │ (Frequency, confidence, evidence set) │
        └────────────┬──────────────────────────┘
                     │
        ┌────────────▼──────────────────────────┐
        │ Output: Decision Report Section       │
        │ (Ranked candidate skills with refs)   │
        └──────────────────────────────────────┘
```

### Workflow

1. **Extract terms** from JD (tokenize, normalize case/punctuation).
2. **Filter stopwords** and low-confidence technical noise.
3. **Match against existing skills** in `skills_matrix.csv`:
   - Exact match → suggest as alias or variant.
   - No match → candidate new skill.
4. **Score candidates** by:
   - Frequency in JD and selected bullets.
   - Evidence count (how many bullets mention it).
   - Semantic cluster (group related terms).
5. **Output to decision report**:
   - Ranked list of candidate skills.
   - Each entry includes: skill name, confidence, source bullets, JD references.

### Acceptance Criteria

- Suggestion output appears in decision report with skill name, confidence, and evidence.
- No automatic mutation of `skills_matrix.csv`.
- Suggestions can be reviewed and accepted/rejected by human reviewer before canonical update.

### Configuration

- **Stopword list**: `config/skill_extraction_stopwords.txt` (if needed).
- **Min confidence threshold**: Configurable (e.g., 0.6).
- **Min evidence count**: Configurable (e.g., 2 sources).

---

## Issue 6: Category Adjustment Suggestions

### Goal
Analyze bullet clusters and suggest category merge/split/rename actions based on observed grouping patterns without auto-applying changes.

### Architecture

```
┌────────────────────────────────────────────┐
│ Canonical Skill Matrix + Selected Bullets  │
└────────────────┬──────────────────────────┘
                 │
     ┌───────────▼───────────┐
     │ Bullet Clustering     │
     │ (Group by category)   │
     └───────────┬───────────┘
                 │
     ┌───────────▼──────────────────────────┐
     │ Intra-cluster Cohesion Analysis      │
     │ (Semantic similarity within groups)  │
     └───────────┬──────────────────────────┘
                 │
     ┌───────────▼──────────────────────────┐
     │ Cross-cluster Overlap Detection      │
     │ (Skills appearing in multiple cats)  │
     └───────────┬──────────────────────────┘
                 │
     ┌───────────▼──────────────────────────┐
     │ Category Action Recommendation       │
     │ (merge/split/rename with rationale)  │
     └───────────┬──────────────────────────┘
                 │
     ┌───────────▼──────────────────────────┐
     │ Output: Decision Report Section      │
     │ (Recommended actions + evidence)     │
     └──────────────────────────────────────┘
```

### Workflow

1. **Cluster bullets** by their assigned category in `skills_matrix.csv`.
2. **Measure cohesion**: Semantic similarity within clusters (e.g., cosine distance on TF-IDF or embeddings).
3. **Detect overlaps**: Skills appearing in multiple categories or uncategorized.
4. **Generate recommendations**:
   - **Merge**: "Cloud DevOps" and "Infrastructure" show 0.85 similarity → consider merging.
   - **Split**: "Business" cluster contains 15 skills with 0.4 internal cohesion → suggest splitting.
   - **Rename**: "Tools" is vague; suggest "Build Tools" or "Version Control".
5. **Output to decision report**:
   - Recommended action (merge/split/rename).
   - Affected categories/skills.
   - Confidence score and evidence (cohesion metrics, overlap count).

### Acceptance Criteria

- Recommendations appear in decision report as review items.
- Accepted recommendations update canonical docs with traceable rationale (link to decision report, date, reviewer).
- No automatic category mutations.

### Configuration

- **Min cohesion threshold**: Configurable (e.g., 0.6 = high cohesion; below 0.5 = consider split).
- **Min overlap threshold**: Configurable (e.g., skill appearing in 2+ categories).
- **Clustering method**: TF-IDF or embeddings-based (configurable).

---

## Decision Report Integration

Both Issue 5 and 6 outputs feed into the **Decision Report** (Issue 4):

```yaml
# decision_report.yaml (example section)
skill_suggestions:
  new_skills:
    - skill: "Kubernetes"
      confidence: 0.85
      evidence:
        jd_refs: ["container orchestration", "K8s"]
        bullet_count: 3
        bullets: ["selected_bullet_id_42", "selected_bullet_id_58"]
    - skill: "Terraform"
      confidence: 0.72
      evidence: {...}
  category_recommendations:
    - action: "merge"
      source_categories: ["Cloud DevOps", "Infrastructure"]
      target_category: "Cloud & Infrastructure"
      rationale: "0.85 semantic similarity; skills overlap"
      confidence: 0.82
    - action: "split"
      source_category: "Business"
      rationale: "Cohesion score 0.41; contains HR, Sales, and Project Mgmt"
      suggestions:
        - "HR & Talent"
        - "Sales & Marketing"
        - "Project Management"
      confidence: 0.78
```

---

## Review Workflow (Governance)

1. **Generate**: Resume generation produces decision report with suggestions.
2. **Review**: Human reviews suggestions in report (+ optional UI).
3. **Accept/Reject**: Reviewer marks each suggestion with decision + optional notes.
4. **Record**: Accepted decisions update canonical data with:
   - Link to decision report source.
   - Timestamp and reviewer name.
   - Rationale/notes.
5. **Audit**: Historic decisions queryable for trend analysis.

### Storage (Out-of-scope for this design, but noted)

- Accepted/rejected suggestion history: Consider lightweight artifact (e.g., `data/suggestion_history.jsonl`).
- Decision report schema: Defined in Issue 4.

---

## Dependencies

- **Issue 3**: Bullet selection engine (provides selected bullets for analysis).
- **Issue 4**: Decision report artifact (container for suggestions).
- **Data files**: `data/skills/skills_matrix.csv`, `experience_db.toml`, selected bullets.

---

## Success Metrics

1. **Coverage**: Suggestions catch >80% of significant new skills observed in target JDs.
2. **Precision**: >70% of suggestions are relevant (human acceptance rate).
3. **Velocity**: Report generation adds <5% to pipeline runtime.
4. **Adoption**: Reviewer accepts/applies ≥50% of category recommendations over time.

---

## Related Issues

- **Issue 5**: New-skill suggestion pipeline (this section).
- **Issue 6**: Category adjustment suggestions (this section).
- **Issue 4**: Decision report artifact (output container).
- **Issue 3**: Bullet selection engine (input data).

---

## References

- `docs/REFERENCE/WORKFLOW_DECISIONS_2026-04-03.md` — Staged architecture and governance principles.
- `docs/REFERENCE/RESUME_PIPELINE_ISSUES_2026-04-03.md` — Full issue backlog.
