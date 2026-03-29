# Session Handoff Guide

See also: `docs/REFERENCE/SESSION_HANDOFF_CHEATSHEET.md`

## Purpose

Session handoffs preserve context across short sessions, reboots, and restarts.
They reduce repeated mistakes, speed up restarts, and improve code quality.

A handoff should capture:
- what changed
- why decisions were made
- what is still open
- the exact next action
- known gotchas

## Where to Save Handoffs

Use one canonical location based on the current work unit:

1. Child issue comment (default)
   - Use when the work is implementation-focused.
   - Best for day-to-day continuity.

2. Pull request comment
   - Use when the work is review/merge-focused.
   - Capture review responses, conflict state, and merge readiness.

3. Epic issue comment
   - Use when the update affects multiple child issues.
   - Capture sequencing, scope changes, and cross-cutting decisions.

Do not rely on chat alone for continuity.

## What Belongs in a Handoff

Use this structure:

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

Guidance:
- Keep bullets short and concrete.
- Include file paths and issue/PR numbers when relevant.
- Keep "Next exact step" to one actionable item.

## Start-of-Session Rehydrate Flow

At the start of a new session:

1. Read the latest handoff on the active issue/PR.
2. Confirm current branch and working tree state.
3. Execute the "Next exact step" first.
4. Re-check acceptance criteria before widening scope.

## End-of-Session Flow

Before ending a session:

1. Confirm branch + status are known.
2. Leave one handoff comment in the canonical location.
3. Include one explicit next action for fast restart.
4. If a mistake repeats, promote it into automation.

## Promote Repeated Lessons

If the same problem appears more than once, encode it in one of:
- test
- pre-commit hook
- CI check
- validation script
- permanent docs

This converts memory into enforceable quality controls.

## Trigger Phrases for Fast Collaboration

Use these prompts to keep the workflow consistent:
- "Create a handoff"
- "Rehydrate from the last handoff"
- "Promote this lesson"

If no target is specified, default to the active child issue.

## Scope Discipline

Use handoffs for session state.
Use docs for durable policy.
Use tests/hooks/CI for enforceable behavior.

Keeping these layers separate avoids document churn and stale guidance.
