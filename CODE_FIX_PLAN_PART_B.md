# Code Fix Plan: Issue #120 Part B (Tomorrow)

## Problem
The current `build_resume.py` implementation shows the `--target-role` value directly in the resume header. This violates the principle that:
1. Company names should NEVER appear on the resume
2. Target role is an INTERNAL optimization hint, not part of the resume output
3. Professional title should be configurable separately from target role

## Current Behavior
```bash
python scripts/build_resume.py --target-role "Graphcore Senior Principal Test Framework Software Engineer"
```
**Results in resume showing:** "Graphcore Senior Principal Test Framework Software Engineer" in the headline

## Desired Behavior
```bash
python scripts/build_resume.py \
  --target-role "Graphcore Senior Principal Test Framework Software Engineer" \
  --professional-title "Senior Staff Software Engineer, Test Automation & Framework Architecture"
```
**Results in resume showing:** "Senior Staff Software Engineer, Test Automation & Framework Architecture" in the headline

## Code Changes Needed

### 1. Update `parse_args()` (line ~199)
Add new optional parameter:
```python
parser.add_argument(
    "--professional-title",
    type=str,
    default="",
    help="Professional title for resume display (if not provided, uses profile headline or derives from target-role)"
)
```

### 2. Update `ResumeIR` dataclass (line ~176)
Add field to track the professional title separately:
```python
professional_title: str = ""  # New field
```

### 3. Update `resolve_headline()` (line ~398)
Change logic to prioritize professional-title over target-role:
```python
def resolve_headline(profile: Profile, target_role: str, professional_title: str = "") -> str:
    """Use professional_title if provided (separate from target-role).

    target_role is for internal LLM optimization only, never shown in output.
    professional_title is what appears on the resume.
    Falls back to profile headline if neither provided.
    """
    # Priority 1: explicit professional_title parameter
    if professional_title.strip():
        return professional_title.strip()

    # Priority 2: profile headline (DO NOT use target_role here)
    return profile.headline
```

### 4. Update `_get_base_role()` (line ~414)
Change to NOT use target_role for display (it's internal only):
```python
def _get_base_role(resume: ResumeIR) -> str:
    """Extract base role label for LLM processing (not for display).

    Uses the priority: target_role > job_context.role_hint > display_headline > profile_headline
    Note: target_role is for LLM context only, never shown in resume output.
    """
    # Priority 1: explicit target_role (for LLM, not display)
    # ... rest unchanged
```

### 5. Update pipeline call (line ~2282 in run_pipeline)
Pass professional_title when building ResumeIR:
```python
resume = ResumeIR(
    profile=profile,
    target_role=args.target_role,
    professional_title=args.professional_title,  # Add this
    # ... rest of fields
)
```

### 6. Update resolve_headline() call
Change the call to pass professional_title:
```python
display_headline = resolve_headline(profile, args.target_role, args.professional_title)
```

## Testing Plan
1. Test with `--professional-title` provided (should show professional title in output)
2. Test without `--professional-title` (should show profile headline)
3. Test with `--target-role` only (should NOT show target role in output, use profile headline)
4. Verify "Graphcore" never appears in output
5. Verify company name never appears in output

## Files to Modify
- `scripts/build_resume.py` — Main code changes
- `scripts/resume_templates.py` — May need updates if templates reference target_role

## Timeline
- Tier 2 improvement, implement after Option A (data improvements) is complete
- Estimate: 30-45 minutes to implement and test
