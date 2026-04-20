# AGENTS_LOCAL.md

Local overrides and branch-scoped guidance layered after `AGENTS.md`.

## Issue Tracking
- Parent rollout: tooling issue #216.
- Consumer adoption: resume-builder issue #47.

## Tooling Promotion Tracking (Required)
- When adding/changing behavior in this consumer repo that is likely to be promoted to `tooling`, create a `tooling` issue first (before editing consumer files).
- After landing the consumer-side change, update that tooling issue with exact details: file paths changed, rule text/logic added, and a short rationale.
- Include the tooling issue link in related PR discussion so promotion work is easy to pick up later.

## PR Review Conventions (Resume-Builder Specific)
- Post PR-thread replies only for GitHub review comments/threads; do not mirror chat-only guidance to PR threads unless the user explicitly asks.
- For every review thread (including resolved/outdated), post a short status update when work is done so audit history is explicit.
- If a review item is deferred or needs clarification, add a PR-thread comment stating why, open a follow-up issue, and include the issue link in that thread.
- If a deferred item is picked up later, add a follow-up thread comment linking both the issue and the fixing PR/commit.

## WSL Path Handling (Windows + WSL Workspace)
This workspace runs on WSL (Ubuntu) but is opened from a Windows JetBrains editor.
File paths surfaced by the editor use Windows UNC format:
- `\\wsl.localhost\Ubuntu\home\<user>\projects\<repo>\...`
- `\\wsl$\Ubuntu\home\<user>\projects\<repo>\...`

Always convert these to native Linux paths before any file edit or git operation:
- `\\wsl.localhost\Ubuntu\home\<user>\projects\<repo>\...` -> `/home/<user>/projects/<repo>/...`
- `\\wsl$\Ubuntu\home\<user>\projects\<repo>\...` -> `/home/<user>/projects/<repo>/...`

Rules enforced for every session:
- When calling `replace_string_in_file`, `insert_edit_into_file`, or `create_file`, always pass the `/home/<user>/...` path; never the UNC path. UNC writes do not reliably reach the Linux filesystem that git tracks.
- When running git or shell commands, always use the native Linux path (`/home/<user>/projects/<repo>`).
- Use `python3` with `subprocess` (not shell heredocs via `run_in_terminal`) for git operations so output is reliably captured and not swallowed by the prompt.
- After any file-tool edit, verify with Python: `open('/home/<user>/.../<file>').read()` to confirm the write landed on the Linux filesystem before staging or committing.
