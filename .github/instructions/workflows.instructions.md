---
applyTo: ".github/workflows/*.yml"
---

# GitHub Actions Workflows — Pinning and Lock Contract

Every `uses:` reference in a workflow under `.github/workflows/` is a supply-chain
trust decision. The repo enforces strict pinning policy via
`scripts/validate_workflow_action_pins.py`, run as `make action-pin-check`.

## Required pin format

- The lock file `.github/workflow-action-lock.json` is the single source of
  truth for which ref each `uses:` entry must use. `validate_workflow_action_pins.py`
  enforces **exact ref equality** between every workflow's `uses:` value
  and the lock entry for that action — it does not parse comments, parse
  semver, or accept a SHA-with-tag-comment fallback. If the workflow ref and
  the lock value differ in any way, the check fails.
- The lock file convention is to use **strict semver tag refs** (e.g.
  `actions/checkout@v6.0.2`, not `@v6` or `@main`). Keep it that way: a
  floating major ref or branch ref in the lock would be silently allowed by
  the validator (it only checks equality), so the strict-tag convention
  must be enforced by humans during review of the lock file itself.
- The validator also fails when a workflow references an action absent from
  the lock, or when the lock contains an entry that no workflow references —
  every locked action must be used, every used action must be locked.

## When you change a workflow ref

1. Bump the version in **both** the workflow file and
   `.github/workflow-action-lock.json` in the same commit.
2. Run `make action-pin-check` locally before requesting review.
3. If you are introducing a new action, add it to the lock file first; the
   validator will reject any workflow that references an unlocked action.

## Other workflow expectations

- Prefer matrix or job-level reuse over copy-pasted steps; keep CI fast.
- Use `concurrency:` with `cancel-in-progress: true` for PR-triggered jobs
  to avoid duplicate runs from the `push` + `pull_request` pair.
- Cache and artifact keys must include enough inputs to invalidate on
  source change (see the existing build job's `docker_inputs.hash`).
- Do not introduce a `GITHUB_TOKEN` env override in a step unless it is
  absolutely required — a stale or wrong token silently shadows the runner's
  default and produces confusing 401s.

## Validation before requesting review

```bash
make action-pin-check
make lint
make agents-drift-check
```
