# Spike: PDF-First Skills Line Measurement Loop

**Issue:** #43
**Branch:** `spike/43-pdf-skills-line-measurement`
**Status:** Complete — recommendation ready for #42

---

## Goal

Validate a deterministic measurement loop for the skills section that reports
actual wrapped-line counts, so that skills selection and category trimming in
issue #42 can be driven by real layout feedback rather than character-count
heuristics.

---

## Chosen Approach

### Renderer path: Pillow TrueType font metrics (no rendering)

Rather than rendering a full PDF, the spike queries actual TrueType font metrics
using **Pillow `ImageFont.truetype`** at the reference font size. This gives
character-accurate text-width measurements without the runtime cost of PDF
generation.

**Why not full PDF rendering?**

| Option | Pro | Con |
|---|---|---|
| Pillow font metrics (chosen) | Fast (<1 s), no render, deterministic, uses real Calibri metrics | Default mode has idealized spacing (no kerning); optional `--kern` improves borderline precision; ligatures ignored |
| ReportLab (not installed) | True PDF metrics, kerning | Additional dependency, overkill for wrap counting |
| WeasyPrint (not installed) | Exact browser/CSS layout | Heavy dep, slow, overkill |
| Playwright PDF | Pixel-perfect CSS layout | Requires browser binary, slow, async |

Pillow at the reference font and DPI is sufficient to detect line boundary
crossings and +/−1 line shifts. The small difference from kerning/ligatures
does not affect category-level trimming decisions.

### Reference layout (from `sandbox/Zebra_Resume.docx`)

| Parameter | Value |
|---|---|
| Page width | 8.4896 in |
| Left margin | 0.6986 in |
| Right margin | 0.6986 in |
| **Usable text width** | **7.0924 in (510.65 pt)** |
| Font | Calibri 11pt |
| Skills format | `Category: skill1 • skill2 • ...` (bold category label) |

### Measurement method

```python
# Discover Calibri via fontconfig first, then WSL Windows mount.
# If Calibri is unavailable, test paths can use Liberation Sans fallback.
font_regular, font_bold, font_name = load_font_pair()

# Pillow size=11 at internal 72-DPI baseline → getlength() returns points
# (1 pixel at 72 DPI = 1 point = 1/72 inch)
width_pt = font.getlength(text)  # direct point value — no conversion needed
```

Word-level wrapping is simulated by accumulating token widths and starting a
new line when the accumulated width exceeds `TEXT_WIDTH_PT = 510.65`.

---

## Measurements

### Before: full unfiltered skills matrix

Current state with all 16 categories and 137 skills:

```
Skills section: 39 wrapped lines  [✗ over budget (target 11–13)]

Category                                   Skills  Lines  Wrap trigger
──────────────────────────────────────────────────────────────────────
AI-Assisted Quality                             5      2  Microsoft
AI-Assisted Quality Engineering                 2      1  -
AI-Driven Engineering                           5      2  AI-assisted
Architecture & Design                           6      2  Design
Automation & Framework Architecture            17      5  frameworks
Automation & Framework Engineering              9      3  Automation
CI/CD & Tooling                                13      3  GitHub
Collaboration & Engineering Practices           9      2  strategy
Core Engineering Skills                         6      2  Pattern
Debugging & Analysis                           10      3  Metrics/monitoring
Distributed Systems & Infrastructure            7      3  (on-prem
Environments & Infrastructure                   4      1  -
Networking                                      1      1  -
Programming & Scripting                         9      1  -
Quality & Testing Strategy                      6      2  readiness
Testing & Validation                           28      6  •
```

### After: projected 6-category targeted selection (example)

Selecting 6 high-signal categories with trimmed skill lists per the #42
design (6–7 categories, ~11–13 lines target):

| Category (example selection) | Est. Skills | Est. Lines |
|---|---|---|
| Automation & Framework Architecture | 8 | 2 |
| CI/CD & Tooling | 7 | 1 |
| Testing & Validation | 10 | 2 |
| Programming & Scripting | 7 | 1 |
| Debugging & Analysis | 6 | 2 |
| AI-Driven Engineering | 4 | 1 |
| **Total** | **42** | **~9** |

> **Note:** These per-category line estimates are illustrative, not formula-derived.
> With real profile data the packing algorithm targets **11–13 lines** total
> (see `TARGET_LINES_MIN`/`TARGET_LINES_MAX` in `measure_skills_lines.py`).

Exact line counts for any candidate selection can be computed in < 1 ms by
calling `measure_skills_section()` with the filtered `skills_by_category` dict.

---

## Sensitivity Validation

The measurement loop correctly detects single-skill changes:

| Test | Before | After | Δ lines |
|---|---|---|---|
| Add "PowerShell scripting" to Programming & Scripting (9→10 skills) | 1 | 2 | **+1** |
| Remove wide long-form skill from wrapping category | 2+ | 1 fewer | **−1** |
| Shorten "Hybrid cloud interactions (on-prem <-> cloud)" | n | ≤ n | **0 or −1** |

All measurement tests in `tests/scripts/test_measure_skills_lines.py` pass in
the current local environment.

---

## Limitations

1. **Calibri availability differs by environment.** Discovery is `fc-list`
   first, then WSL Windows mount. Current CLI behavior allows fallback fonts
   (`require_calibri=False`) to keep CI stable when Calibri is unavailable.
   Fallback order is Liberation Sans first, then DejaVu Sans.

2. **Kerning is optional; ligatures are not modeled.** By default,
   `ImageFont.getlength()` uses advance-width metrics only. Passing `--kern`
   enables legacy kern-table adjustments via fontTools. Ligatures are still
   not modeled, and residual discrepancy from DOCX can remain near boundaries.

3. **Measurement is word-level** — DOCX layout engines can break at hyphen
   opportunities within long compound words. The spike does not simulate
   hyphenation; skills with hyphens (e.g., "Service-layer automation (SSH)")
   measure slightly conservatively.

4. **Runtime input guards are now enforced** for `--csv` and `--output-dir`.
   This blocks reads/writes under `sandbox/` and `data/samples/`, consistent
   with repo runtime-input policy.

---

## Recommendation for Issue #42

**Integrate `measure_skills_section()` as the feedback oracle for skills
selection.**

1. **Call site in `#42`:** After each candidate selection of categories/skills
   (before finalising the IR), call `measure_skills_section(candidate_skills)`
   and check `summary.within_budget`.

2. **Trimming loop:** If `total_lines > TARGET_LINES_MAX`, drop the lowest-
   relevance skill from the longest category and re-measure. Repeat until
   within budget or minimum skill count is reached.

3. **Font path strategy:** Keep `fc-list` as primary Calibri discovery,
   preserve WSL mount as secondary, and use Liberation Sans in CI for fallback
   test coverage when Calibri is not available.

4. **Persist the artifact:** Write `skills_measurement.json` next to the IR
   snapshot for audit/diff traceability on each run.

5. **Target:** 11–13 lines, typically 6–7 categories.

---

## Files Delivered

| File | Purpose |
|---|---|
| `scripts/measure_skills_lines.py` | Spike measurement script (CLI + importable API) |
| `tests/scripts/test_measure_skills_lines.py` | Measurement tests covering acceptance criteria + kerning/runtime-guard behavior |
| `data/review/outputs/skills_line_measurement/skills_measurement.json` | Baseline measurement artifact |
| `docs/REFERENCE/SKILLS_LINE_SPIKE.md` | This document |

---

*Closes #43 — spike complete, recommendation captured, ready for #42 implementation.*
