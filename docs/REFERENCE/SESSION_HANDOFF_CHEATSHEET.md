# Session Handoff Cheat Sheet

See full guide: `docs/REFERENCE/SESSION_HANDOFF_GUIDE.md`

## Use This Prompt

- "Create a handoff"

Optional target:
- "Create a handoff on issue <number>"
- "Create a handoff on PR <number>"
- "Create an epic handoff on issue <number>"

## Save Location Rules

- Default: active child issue comment
- PR-heavy session: PR comment
- Cross-child/strategy change: epic issue comment

## Handoff Template

```md
## Session handoff

### Done
-

### Decisions
-

### Open problems
-

### Next exact step
-

### Gotchas
-
```

## Start-of-Session Prompt

- "Rehydrate from the last handoff"

## Promotion Rule

If a gotcha repeats, convert it into:
- test, or
- pre-commit/CI check, or
- validation script, or
- permanent docs update

Prompt:
- "Promote this lesson"

## One-Line Quality Rule

Session notes track current state; automation and docs preserve long-term learning.
