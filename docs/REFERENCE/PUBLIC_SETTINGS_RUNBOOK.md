# Public Settings Runbook

Use this runbook for issue #99 before changing repository visibility to public.

## Scope

This runbook covers:
1. GitHub repository/security settings that should be in place before the visibility flip.
2. Rewrite-window controls so history cleanup is coordinated and auditable.
3. Post-flip validation checks.
## Preconditions

- The active execution branch strategy is `epic/99-public-readiness` with child branches merged into epic first.
- Current HEAD sanitization changes are merged into `epic/99-public-readiness`.
- The owner has approved proceeding with the public-readiness window.
## 1) GitHub Settings Checklist (Before Public)

Complete these in repository Settings before changing visibility:
- [ ] Branch protection/ruleset on `main` requires pull requests.
- [ ] Required checks are enabled for merge to `main`.
- [ ] At least one review approval is required on PRs.
- [ ] Dismiss stale approvals on new commits.
- [ ] Restrict force-push to `main` (rewrite window handled explicitly).
- [ ] Enable Dependabot alerts.
- [ ] Enable Dependabot security updates.
- [ ] Enable and configure code scanning (CodeQL or equivalent) where applicable.
- [ ] Confirm Actions default token permissions are least-privilege.
- [ ] Confirm no static credentials are stored in workflows/scripts.
- [ ] Enable secret scanning and push protection where available for this repository visibility/tier.
- [ ] If secret scanning or push protection is unavailable, record the limitation and compensating controls on issue #99.
## 2) Rewrite Window Checklist

Use a short maintenance window for the full rewrite.
- [ ] Post a freeze note on issue #99 with planned start/end times.
- [ ] Pause non-#99 merges during the rewrite window.
- [ ] Tag/backup current refs before rewrite.
- [ ] Execute approved history rewrite plan.
- [ ] Force-push rewritten refs.
- [ ] Verify removed paths/content are no longer present in history.
- [ ] Post collaborator reset instructions (fresh clone or hard reset guidance).
## 3) Post-Rewrite Validation

- [ ] `main` and `epic/99-public-readiness` point to expected commits.
- [ ] PR checks pass after rewritten history is in place.
- [ ] No blocked/sensitive paths are present in current tracked files.
- [ ] Smoke-run key commands (`make check`, selected tests) succeed.
- [ ] Issue #99 has explicit "go/no-go: approved" comment.
## 4) Visibility Flip + Post-Flip Smoke Check

- [ ] Change repository visibility to public.
- [ ] Confirm landing page/README renders correctly.
- [ ] Confirm no private/sensitive docs or artifacts are exposed.
- [ ] Confirm PR and branch protection still enforce expected policy.
- [ ] Post final completion note on issue #99 with links to evidence.
## Evidence to attach on #99

- Link to epic PR.
- Link to rewrite commands/log summary.
- Screenshots or notes for key settings.
- Post-flip smoke-check results.
