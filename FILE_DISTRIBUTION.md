# File Distribution for Managed Sync Contract

## Summary

This document explains which files are owned by the tooling repository, which
files are synced into consumer repos, and how the manifest + lock contract
controls that lifecycle.

## Source of Truth

Managed-file ownership is defined by two artifacts:
- `.tooling-sync-manifest.toml` at the root of this tooling repo — declares the desired set of files that may be synced
- `.tooling-sync-manifest.lock` in each consumer repo — records the managed files actually applied during the most recent successful sync

The manifest defines **what should be managed**.
The lock records **what is currently managed in that consumer**.

## Distribution Plan

### Files in `tooling/` repo

**Eligible for sync into projects:**
- Only files explicitly listed in `.tooling-sync-manifest.toml`
- Typical examples include shared docs, scripts, workflow helpers, and repo-wide config files
- Shared agent guidance such as `AGENTS.md` when present in the manifest
- Shared GitHub workflows under `.github/workflows/` when listed in the manifest
- Shared workflow regression tests under `tests/workflows/` when listed in the manifest

**Tooling repo only (not auto-synced):**
- `scripts/sync_tooling.sh` — bootstrap/security-sensitive; consumers update this manually
- `pyproject.toml` — tooling-side config source, not copied directly into consumers
- `project-template/` — scaffolding for new projects only
- Any file omitted from `.tooling-sync-manifest.toml`

### Files in each consumer project

**Consumer-owned identity files (never synced):**
- `VERSION`
- `pyproject.toml` (generated from project metadata + tooling config)
- `.pyproject.meta.toml`
- `tooling.toml`
- `README.md`
- `CHANGELOG.md`
- `requirements.txt`
- `scripts/sync_tooling.sh`

**Managed files synced from tooling:**
- Only files declared in `.tooling-sync-manifest.toml`
- After sync, those files are recorded in `.tooling-sync-manifest.lock`
- These files are subject to drift validation via `make drift-check`

## Managed File Lifecycle

### First sync
- Sync copies manifest-declared files into the consumer repo
- Sync writes `.tooling-sync-manifest.lock`
- No stale-file deletion occurs on first sync because no prior lock baseline exists

### Subsequent syncs
- Sync refreshes all manifest-declared files
- Sync compares the previous lock file with the current manifest
- Files that were previously managed but are no longer in the manifest become stale-file candidates
- By default, those stale managed files are removed and reported as `REMOVED: <path>`

### Non-destructive rollout mode
If you want to inspect stale-file candidates before deleting them:
- run sync with `--no-delete`, or
- set `SYNC_NO_DELETE=1`

In that mode, stale managed files are preserved and reported as:
- `SKIPPED REMOVAL (--no-delete): <path>`

## Safety Rules

- Only files listed in the **previous lock** are ever candidates for stale-file deletion
- User-created files that were never managed by sync are never removed
- Unsafe stale paths (for example `../escape.txt`) are skipped with a security warning
- Symlinked stale targets are skipped with a security warning instead of being deleted
- Drift validation treats missing/invalid lock state as a contract problem, not a normal missing-file case

## Updating `scripts/sync_tooling.sh` in Consumer Projects

When `scripts/sync_tooling.sh` changes in tooling:
1. Consumer projects do **not** receive it automatically
2. Manual update is required
3. Review the script before copying because it is bootstrap/security-sensitive

This intentional exception prevents a compromised tooling source from silently
changing the script that controls future sync behavior.

## Practical Workflow

1. Commit tooling changes first
2. Update `.tooling-sync-manifest.toml` when the managed-file set changes
3. Sync consumer repos
4. Re-run `make drift-check`
5. If you need to inspect stale-file removals before applying them, repeat sync with `--no-delete`
6. Commit the resulting managed files + lock updates in the consumer repo

## See Also

- `docs/REFERENCE/SYNC_MANIFEST.md` — sync contract, enforcement, remediation, and deletion behavior
- `scripts/sync_tooling.sh` — implementation of sync + stale-file handling
- `scripts/validate_sync_drift.py` — managed-file drift validator
