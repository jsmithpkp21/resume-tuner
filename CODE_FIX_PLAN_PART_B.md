# Code Fix Plan: Issue #120 Part B (Historical / Follow-up)
## Status Update (as of PR #123)
PR #123 already changed resume headline rendering so `--target-role` is **not** shown in
visible output. `target_role` remains an internal tailoring hint.
## Historical Context
This plan was originally drafted when `--target-role` could leak into the displayed
headline. That specific behavior is now fixed.
## Remaining Optional Improvement
A separate `--professional-title` argument is still a potential enhancement, but it is no
longer required to prevent company/target-role leakage.
## Current Behavior
```bash
python scripts/build_resume.py \
  --target-role "Graphcore Senior Principal Test Framework Software Engineer"
```
Expected display behavior:
- Resume headline comes from profile/display headline logic
- `--target-role` is used for internal tailoring signals only
- Target company names should not appear in the visible headline
## Future Enhancement (Optional)
If implemented later, `--professional-title` should:
1. control display headline text explicitly, and
2. remain separate from `--target-role` internal context.
## Suggested Validation
1. Build with `--target-role` containing company text.
2. Confirm rendered headline does not show target-role/company text.
3. Confirm profile headline (or explicit display title, if added later) is shown.
## Files That Would Be Touched (if optional enhancement is implemented)
- `scripts/build_resume.py`
- tests covering headline rendering and output policy
