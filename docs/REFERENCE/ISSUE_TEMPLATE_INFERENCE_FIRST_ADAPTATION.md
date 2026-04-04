# Issue Template: Inference-First, Rule-Backed Adaptation
## Problem
- What JD-driven framing behavior is currently missing or incorrect?
- Which outputs show hardcoded behavior or weak adaptation?
## Goal
Implement inference-first adaptation that:
- infers framing from JD signals (scope, level, domain, constraints, delivery model)
- uses generic fallback rules only when inference confidence is low
- remains domain-agnostic and extensible
## Scope
- [ ] JD signal extraction inputs/outputs
- [ ] Confidence threshold and fallback trigger
- [ ] Generic fallback rules (facts preserved, tone adaptation, evidence match)
- [ ] Rationale trace in output
## Out of Scope
- Hardcoded role-specific mapping tables
- Canonical data mutation based on a single JD
- Domain-specific one-off logic in selection core
## Acceptance Criteria
- [ ] Given same canonical data + same JD, output is deterministic
- [ ] No generated claim exceeds canonical evidence
- [ ] Fallback usage is explicit in rationale trace
- [ ] New domain signals can be added without changing core selection algorithm
## Validation
- [ ] Add/update tests for inference path and fallback path
- [ ] Add at least one non-software JD fixture to verify domain-agnostic behavior
- [ ] Confirm canonical `experience_db.toml` remains unchanged during generation
## References
- `docs/REFERENCE/SELECTION_ENGINE_DESIGN.md`
- `data/review/reviewer_notes.csv` (`design-003`, `design-004`)
