<!-- Source of truth for agent instructions. Changes here must be reflected in .github/copilot-instructions.md -->

# AGENTS.md

## Quick Commands
```bash
make setup
make lint
make test
make check
make sync-tooling
make drift-check
pytest -q tests/scripts/test_consumer_contract.py
```

## Planning Gate (Required)
- Do not make file/code changes until the user explicitly says: `plan ready`.
- Use a two-phase flow: (1) inspect + propose plan, (2) implement only after `plan ready`.
- If requirements conflict, ask for clarification before changing files.

## Local Overrides (`AGENTS_LOCAL.md`)
- `AGENTS.md` remains the synced baseline contract from tooling.
- `AGENTS_LOCAL.md` is optional and consumer/local-branch owned for repo-specific overrides or additions.
- When both files exist, apply `AGENTS.md` first, then apply `AGENTS_LOCAL.md` as additive/override guidance.
- Never add `AGENTS_LOCAL.md` to the tooling source repo root `.tooling-sync-manifest.toml`; the tooling repo's copy is authoritative and consumers must not edit theirs, so local guidance must remain outside managed sync to avoid drift churn.

## Adding consumer-specific make targets (`Makefile.local`)
- The synced `Makefile` ends with `-include Makefile.local`. The leading `-` means make tolerates the file's absence, so this is a no-op when no local targets exist.
- `Makefile.local` is consumer-owned. Use it for repo-specific targets that wrap consumer-only scripts or data and have no place in the shared tooling Makefile. Consumers may check it in or list it in `.gitignore`, per repo preference.
- `Makefile.local` MUST NOT be added to `.tooling-sync-manifest.toml`. Listing it would let tooling sync overwrite consumer targets and would also surface every consumer-side edit as a `make drift-check` failure — defeating the entire reason this hook exists.
- Editing the synced tooling `Makefile` directly in a consumer repo to add consumer-only targets remains forbidden by `make drift-check`; `Makefile.local` is the only sanctioned extension point.

## Path-Scoped Instructions (`.github/instructions/*.instructions.md`)
- Files under `.github/instructions/` use frontmatter `applyTo:` globs to surface narrower guidance when the agent edits a matching path. They restate (not replace) rules already in `AGENTS.md`, so the agent re-reads critical invariants when deep in a sensitive file.
- Current scoped files: `scripts.instructions.md` (security invariants for `scripts/sync_tooling.sh`), `workflows.instructions.md` (action pin and lock contract for `.github/workflows/*.yml`).
- When you add a new scoped file, add it to `.tooling-sync-manifest.toml` so consumers receive it.
- Drift between `AGENTS.md` and `.github/copilot-instructions.md` is enforced by `make agents-drift-check` (run in CI as part of the verify job).

## Project Purpose
- `tooling` is the upstream source for shared automation consumed by repos like `base_repo`.
- The core contract is deterministic environments plus managed sync: this repo defines files, consumers apply them.

## Architecture You Need First
- Environment lifecycle is shell-first: `scripts/create_env.sh` creates and `scripts/verify_env.sh` verifies against metadata.
- Sync is allow-list driven: the source-of-truth manifest lives in the tooling source repo root `.tooling-sync-manifest.toml`. The tooling repo's copy is authoritative; consumers may carry the file (it was historically synced and is referenced by tests/docs) but must not edit it, and they record applied state in `.tooling-sync-manifest.lock`.
- `scripts/sync_tooling.sh` is bootstrap/security-sensitive (path traversal checks, symlink protections, lock-writing, stale-file handling).
- `pyproject.toml` is generated in consumers via `scripts/merge_pyproject.py` + `.pyproject.meta.toml`; tooling provides the config schema and template only.
- Service boundary matters: tooling changes flow outward through sync; consumer identity files do not flow back automatically.

## Critical Workflows (Use These Targets)
- Local bootstrap: `make setup`.
- Daily quality loop: `make lint`, `make test`, `make check`.
- Contract checks before release/sync: `make drift-check`, `make version-check`, `make action-pin-check`, `make docs-check`, `make agents-drift-check`.
- Validate sync behavior after manifest/script edits: run `tests/scripts/test_sync_tooling_regressions.py` (tooling source repo; not present in consumers).
- Docker parity path: `make docker-up` then run normal make targets inside container.

## Repo-Specific Conventions
- Virtualenv path is stable and repo-derived: `~/envs/<repo>-env` (no VERSION suffix).
- Python version source of truth is `tooling.toml` `[python].version`; scripts only fall back when needed.

## Enforced Policies in This Repo Family
- Conventional commits are mandatory here and in synced consumers; enforcement is via `scripts/run_commitlint.sh` + `commitlint.config.mjs` in hooks and CI.
- Direct commit/push to `main` is blocked by `.pre-commit-config.yaml`; use feature/epic branches and PRs.
- Local developer tooling is **local-runtime-first with Docker fallback** (see `docs/REFERENCE/adr/0001-local-tooling-runtime-policy.md`). `make markdown-lint` and `scripts/run_commitlint.sh` both follow this resolution order: pinned local runtime → pinned Docker fallback → hard-fail with remediation. Fully containerized workflows are an explicit opt-in via the `*-docker` make targets (`lint-docker`, `test-docker`, `check-docker`). Any new local tool that shells out to `docker` must satisfy the six invariants in ADR-0001 (pinned runtime, pinned image, hardened installs, sentinel exit code separating setup vs validation failure, actionable hard-fail, cached install artifacts on hot paths).
- GitHub Actions must use strict semver tag pins (`@vX.Y.Z`, for example `actions/checkout@v6.0.2`); floating major pins such as `@v6` are not allowed. Keep refs aligned with `.github/workflow-action-lock.json`.

## Execution Guardrails for Agents
- Keep changes minimal and scoped; do not bundle unrelated refactors in the same PR.
- Branch base policy: create new issue branches from `main` by default; if the issue is an epic child issue, create/rebase from the active `epic/*` branch instead.
- Treat `pyproject.toml` as generated in consumers: update `.pyproject.meta.toml` or tooling inputs and regenerate via `scripts/merge_pyproject.py`.
- Preserve sync security invariants in `scripts/sync_tooling.sh` (path traversal checks, symlink protections, fail-closed behavior) and add tests for any behavior change.
- When changing managed-file scope: in the **tooling source repo**, update `.tooling-sync-manifest.toml`, related docs (for example `FILE_DISTRIBUTION.md`), and `tests/scripts/test_sync_tooling_regressions.py`; in **consumer repos**, run `make sync-tooling`, `make drift-check`, and `pytest -q tests/scripts/test_consumer_contract.py` to validate the applied sync.
- Validate touched areas with targeted tests first, then run broader repo checks (`make lint`, `make test`, or `make check` as appropriate).
- Prefer issue-linked branches when work maps to an issue: `make branch ISSUE=<num>` creates `<type>/<issue>-<slug>` from labels and title.
- When presenting multiple implementation options, include concise pros and cons for each option so trade-offs are explicit.
- Before using `gh` CLI in any script or make target, add `gh auth status` as an explicit preflight with a clear error and remediation message. A stale or expired `GITHUB_TOKEN` env var silently overrides stored credentials and causes HTTP 401 errors.
- Never export `GITHUB_TOKEN` as a static value in dotfiles (`~/.bashrc`, `~/.bash_profile`, etc.). Use `gh auth login` for persistent credentials. If a token must be in the environment, scope it to the session only.

## Integration Points
- Consumer sync path: sibling `../tooling` checkout or explicit `TOOLING_DIR`; GitHub-source sync mode intentionally fails fast.
- Managed-file scope is explicit: update tooling repo root `.tooling-sync-manifest.toml` whenever shared files are added/removed.
- CI/workflow behavior is repo-name dynamic (see `docs/REFERENCE/DYNAMIC_WORKFLOWS.md`, `.github/workflows/*.yml`).
- Release metadata integration: sync can update consumer `.release-please-config.json` from `.pyproject.meta.toml` package name.

## Tooling Promotion Policy (Consumer → Tooling)
When a change made in a consumer repo (for example `resume-builder`) is a candidate for standardization across the repo family, follow this order so the pattern can be promoted into `tooling` quickly and without rediscovery:

1. **Open a tooling tracking issue first.** Before merging the consumer-side change, create an issue in the `tooling` repo describing the candidate rule, its motivation, and which consumer repo originated it. Link the consumer PR (or planned PR) from that issue.
2. **Land the consumer change.** Implement and merge the immediate fix/feature in the consumer repo so the team is unblocked. Reference the tooling issue from the consumer PR description.
3. **Post a promotion comment on the tooling issue** as soon as the consumer change merges. Include exactly what was added: file paths touched, the rule text or code that should be promoted, and a one-line rationale. This turns the tooling issue into a ready-to-implement spec rather than a re-investigation.
4. **Cross-link.** When the tooling-side change ships, comment on the original consumer PR with a link to the tooling PR/commit so the audit trail is closed in both directions.

This policy applies whether the consumer change is a doc, a workflow tweak, a Makefile target, or a script — anything that other repos in the family would benefit from. If the change is genuinely consumer-specific (e.g. resume content, project-specific data), no tooling issue is needed.

## PR Review Conventions

- When reviewing a PR whose branch starts with `copilot/`, the changes were authored by GitHub Copilot's SWE agent. Post review comments directed at `@copilot` so the agent receives and acts on the feedback.
- When you (the agent) authored the changes yourself, implement fixes directly in the branch without @copilot direction. The rule of thumb: if `git log` shows your own commit, fix it; if the branch starts with `copilot/`, comment at @copilot.
- Post PR-thread replies only for GitHub review comments/threads; do not mirror chat-only guidance to PR threads unless the user explicitly asks.
- For every review thread (including resolved/outdated), post a short status update when work is done so audit history is explicit.
- If a review item is deferred or needs clarification, add a PR-thread comment stating why, open a follow-up issue, and include the issue link in that thread.
- If a deferred item is picked up later, add a follow-up thread comment linking both the issue and the fixing PR/commit.

## WSL Path Handling (Windows + WSL Workspace)
This workspace runs on WSL (Ubuntu) but is opened from a Windows JetBrains editor.
File paths surfaced by the editor use Windows UNC format:
	\\wsl.localhost\Ubuntu\home\<user>\projects\<repo>\...
	\\wsl$\Ubuntu\home\<user>\projects\<repo>\...
**Always convert these to native Linux paths before any file edit or git operation:**
	//wsl.localhost/Ubuntu/home/<user>/projects/<repo>/...  ->  /home/<user>/projects/<repo>/...
	\\wsl$\Ubuntu\home\<user>\projects\<repo>\...   ->  /home/<user>/projects/<repo>/...
Rules enforced for every session:
- When calling `replace_string_in_file`, `insert_edit_into_file`, or `create_file`, always pass
  the `/home/<user>/...` path - never the UNC path. UNC writes do not reliably reach the Linux
  filesystem that git tracks.
- When running git or shell commands, always use the native Linux path (`/home/<user>/projects/<repo>`).
- Use `python3` with `subprocess` (not shell heredocs via `run_in_terminal`) for git operations
  so output is reliably captured and not swallowed by the prompt.
- After any file-tool edit, verify with Python: `open('/home/<user>/.../<file>').read()` to confirm
  the write landed on the Linux filesystem before staging or committing.

## Files to Read Before Editing Core Logic
- `Makefile`
- `scripts/sync_tooling.sh`
- `.tooling-sync-manifest.toml` (tooling source repo is authoritative; consumer copies must not be edited)
- `FILE_DISTRIBUTION.md`
- `docs/REFERENCE/SYNC_MANIFEST.md`
- `docs/REFERENCE/PYPROJECT_ARCHITECTURE.md`
- `tests/scripts/test_sync_tooling_regressions.py` (tooling source repo; not present in consumers)
