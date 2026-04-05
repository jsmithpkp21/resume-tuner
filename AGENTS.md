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

## Project Purpose
- `tooling` is the upstream source for shared automation consumed by repos like `base_repo`.
- The core contract is deterministic environments plus managed sync: this repo defines files, consumers apply them.

## Architecture You Need First
- Environment lifecycle is shell-first: `scripts/create_env.sh` creates and `scripts/verify_env.sh` verifies against metadata.
- Sync is allow-list driven: `.tooling-sync-manifest.toml` is the only list of managed files; consumers record applied state in `.tooling-sync-manifest.lock`.
- `scripts/sync_tooling.sh` is bootstrap/security-sensitive (path traversal checks, symlink protections, lock-writing, stale-file handling).
- `pyproject.toml` is tooling-owned config input; consumers should generate their `pyproject.toml` via `scripts/merge_pyproject.py` + `.pyproject.meta.toml`.
- Service boundary matters: tooling changes flow outward through sync; consumer identity files do not flow back automatically.

## Critical Workflows (Use These Targets)
- Local bootstrap: `make setup`.
- Daily quality loop: `make lint`, `make test`, `make check`.
- Contract checks before release/sync: `make drift-check`, `make version-check`, `make action-pin-check`, `make docs-check`.
- Validate sync behavior after manifest/script edits: run `tests/scripts/test_sync_tooling_regressions.py`.
- Docker parity path: `make docker-up` then run normal make targets inside container.

## Repo-Specific Conventions
- Virtualenv path is stable and repo-derived: `~/envs/<repo>-env` (no VERSION suffix).
- Python version source of truth is `tooling.toml` `[python].version`; scripts only fall back when needed.

## Enforced Policies in This Repo Family
- Conventional commits are mandatory here and in synced consumers; enforcement is via `scripts/run_commitlint.sh` + `commitlint.config.mjs` in hooks and CI.
- Direct commit/push to `main` is blocked by `.pre-commit-config.yaml`; use feature/epic branches and PRs.
- `make markdown-lint` is intentionally local-binary first and Docker fallback second, matching the `Makefile`: fast when `markdownlint` is already installed (for example inside the project container), but still runnable on machines that only have Docker.
- GitHub Actions must use strict semver tag pins (`@vX.Y.Z`, for example `actions/checkout@v6.0.2`); floating major pins such as `@v6` are not allowed. Keep refs aligned with `.github/workflow-action-lock.json`.

## Execution Guardrails for Agents
- Keep changes minimal and scoped; do not bundle unrelated refactors in the same PR.
- Treat `pyproject.toml` as generated in consumers: update `.pyproject.meta.toml` or tooling inputs and regenerate via `scripts/merge_pyproject.py`.
- Preserve sync security invariants in `scripts/sync_tooling.sh` (path traversal checks, symlink protections, fail-closed behavior) and add tests for any behavior change.
- When changing managed-file scope, update `.tooling-sync-manifest.toml`, related docs (for example `FILE_DISTRIBUTION.md`), and regression coverage in `tests/scripts/test_sync_tooling_regressions.py` together.
- Validate touched areas with targeted tests first, then run broader repo checks (`make lint`, `make test`, or `make check` as appropriate).
- Prefer issue-linked branches when work maps to an issue: `make branch ISSUE=<num>` creates `<type>/<issue>-<slug>` from labels and title.
- When presenting multiple implementation options, include concise pros and cons for each option so trade-offs are explicit.
- Before using `gh` CLI in any script or make target, add `gh auth status` as an explicit preflight with a clear error and remediation message. A stale or expired `GITHUB_TOKEN` env var silently overrides stored credentials and causes HTTP 401 errors.
- Never export `GITHUB_TOKEN` as a static value in dotfiles (`~/.bashrc`, `~/.bash_profile`, etc.). Use `gh auth login` for persistent credentials. If a token must be in the environment, scope it to the session only.

## Integration Points
- Consumer sync path: sibling `../tooling` checkout or explicit `TOOLING_DIR`; GitHub-source sync mode intentionally fails fast.
- Managed-file scope is explicit: update `.tooling-sync-manifest.toml` whenever shared files are added/removed.
- CI/workflow behavior is repo-name dynamic (see `docs/REFERENCE/DYNAMIC_WORKFLOWS.md`, `.github/workflows/*.yml`).
- Release metadata integration: sync can update consumer `.release-please-config.json` from `.pyproject.meta.toml` package name.

## PR Review Conventions

- When reviewing a PR whose branch starts with `copilot/`, the changes were authored by GitHub Copilot's SWE agent. Post review comments directed at `@copilot` so the agent receives and acts on the feedback.
- When you (the agent) authored the changes yourself, implement fixes directly in the branch without @copilot direction. The rule of thumb: if `git log` shows your own commit, fix it; if the branch starts with `copilot/`, comment at @copilot.
- For every review thread (including resolved/outdated), post a short status update when work is done so audit history is explicit.
- If a review item is deferred or needs clarification, add a PR-thread comment stating why, open a follow-up issue, and include the issue link in that thread.
- If a deferred item is picked up later, add a follow-up thread comment linking both the issue and the fixing PR/commit.
