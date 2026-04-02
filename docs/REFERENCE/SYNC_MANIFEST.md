# Sync Manifest: Allow-List Contract
## Overview
`sync_tooling.sh` uses an **explicit allow-list** to determine which files are
synced from the tooling repo into consumer projects. The allow-list is declared
in `.tooling-sync-manifest.toml` at the root of the tooling repo.
Only files listed in the manifest are ever synced. Nothing is inferred from
exclusions. If a file is not listed, it is not synced — regardless of whether
it exists in the tooling repo.

The allow-list and the lock file work together:
- `.tooling-sync-manifest.toml` defines the **desired managed-file set** from tooling
- `.tooling-sync-manifest.lock` records the **applied managed-file set** in a consumer after a successful sync

---
## Manifest File
**Location:** `.tooling-sync-manifest.toml` (tooling repo root)
**Format:**
```toml
[manifest]
version = "1"
[sync]
files = [
  "path/to/file.ext",
  "another/file.md",
]
```
- `[manifest].version` — schema version (currently `"1"`). Reserved for future
  migration tooling.
- `[sync].files` — array of repo-relative paths to sync. Paths must:
  - Use forward slashes (`/`)
  - Be relative to the tooling repo root (no leading `/`)
  - Not contain `..` (parent directory traversal)
---
## Lock File
Every successful sync also writes `.tooling-sync-manifest.lock` into the
consumer repo root. This file is machine-generated JSON and records the exact
managed-file state that was synced.

**Required fields:**
- `schema_version` — lock schema version (currently `1`)
- `generated_at_utc` — UTC timestamp when the lock was written
- `requested_ref` — ref the consumer asked to sync (for example `v1.7.8` or `main`)
- `resolved_ref` — immutable commit SHA when sync ran from a git checkout; `null`
  for filesystem/archive mode where no git metadata exists
- `source_mode` — `git` or `filesystem`
- `files` — object keyed by repo-relative managed path, each with a `sha256`

**Optional fields:**
- `tooling_repo` — identifier for the tooling repository that served as the
  source of truth for the sync. This is typically the Git remote URL for git
  mode and may be omitted when sync runs from a filesystem/archive source where
  no stable repository identifier is available.

**Example:**
```json
{
  "schema_version": 1,
  "generated_at_utc": "2026-03-13T15:10:00Z",
  "requested_ref": "v1.7.8",
  "resolved_ref": "0123456789abcdef0123456789abcdef01234567",
  "source_mode": "git",
  "tooling_repo": "git@github.com:jsmithpkp21/tooling.git",
  "files": {
    "Makefile": {
      "sha256": "..."
    }
  }
}
```
---
## End-to-End Workflow
Typical managed-file lifecycle for a consumer repo:
1. Run sync (`make sync-tooling` or `bash ../tooling/scripts/sync_tooling.sh <ref> .`)
2. Sync copies all manifest-declared files into the consumer repo
3. Sync writes/refreshes `.tooling-sync-manifest.lock`
4. Optional stale managed files are removed if they existed in the prior lock but are no longer in the current manifest
5. Local pre-push and CI drift checks validate current managed files against the lock
6. If drift is reported, re-run sync, review intentional changes, and then re-run checks

If you need a non-destructive rollout while reviewing stale-file changes, run sync with deletion disabled:

```bash
bash ../tooling/scripts/sync_tooling.sh <ref> . --no-delete
```

Or set the environment variable:

```bash
SYNC_NO_DELETE=1 bash ../tooling/scripts/sync_tooling.sh <ref> .
```

---
## Drift Validation
Consumers can validate managed files against the lock with:

```bash
make drift-check
```

This runs `scripts/validate_sync_drift.py --root .` and reports one of:

| Status | Meaning | Exit code |
|--------|---------|-----------|
| `OK` | Lock is valid; all managed files exist and match their hashes | `0` |
| `DRIFT` | A managed file exists but its contents differ from the lock | `1` |
| `MISSING` | A managed file listed in the lock is absent | `1` |
| `MALFORMED` | Lock is missing, unreadable, or invalid | `2` |
| `SECURITY` | Lock or managed file fails security checks (for example, path escapes repo root or unsafe symlink) | `2` |

A missing `.tooling-sync-manifest.lock` is treated as `MALFORMED`, not
`MISSING`. That distinction matters because the validator cannot establish the
managed-file contract at all when the lock itself is absent or broken. Both
`MALFORMED` and `SECURITY` map to exit code `2`; `SECURITY` is used when the
validator detects an unsafe condition (for example, a managed path that escapes
the repo root or a disallowed symlink) that prevents validation from running
safely.

**Remediation guidance:**
- `DRIFT` / `MISSING` — re-run sync-tooling to restore managed files, or update
  tooling source and regenerate the lock intentionally.
- `MALFORMED` — re-run sync-tooling to initialize or repair the lock file.
- `SECURITY` — investigate and remove unsafe paths or symlinks (for example,
  managed files that resolve outside the repo root), then re-run sync-tooling
  to regenerate a safe lock file. Do not auto-fix `SECURITY` findings in CI
  without human review.

**Recovery playbook:**
1. Re-run sync from the intended tooling ref.
2. Re-run `make drift-check` locally.
3. If stale-file removals are expected but you want to inspect them first, repeat the sync with `--no-delete` or `SYNC_NO_DELETE=1`.
4. Resolve any reported `SECURITY` findings manually before regenerating the lock.
5. Re-run push/CI once drift-check returns `OK`.

## Enforcement Paths
- **Pre-push enforcement:** `.pre-commit-config.yaml` runs `tooling-drift-check`
  at push stage using `scripts/validate_sync_drift.py --root .`.
- **CI enforcement:** `.github/workflows/verify-environment.yml` runs
  `make drift-check` in the `verify` job.

When enforcement fails, use this recovery path:
1. Run `make sync-tooling` (or your normal sync command) to refresh managed files.
2. Re-run `make drift-check` locally and confirm exit code `0`.
3. Re-run push/CI after lock and managed files are back in sync.
---
## Fail-Fast Validation
The sync script validates the manifest at startup before copying any files:
| Condition | Behaviour |
|-----------|-----------|
| Manifest file is missing | `exit 1` with clear error |
| Manifest is invalid TOML | `exit 1` with parse error |
| `[sync].files` is empty or absent | `exit 1` with clear error |
| A declared path does not exist in the tooling source at the requested version | `exit 1` listing all missing entries |
This means: if the manifest declares a file that hasn't been committed yet (or
has been deleted), the sync will refuse to run until the manifest is corrected.
---
## Adding a File to Sync
1. Add the file to the tooling repo (commit it).
2. Add its repo-relative path to `[sync].files` in `.tooling-sync-manifest.toml`.
3. Commit both changes together in the same PR.
---
## Removing a File from Sync
1. Remove the path from `[sync].files` in `.tooling-sync-manifest.toml`.
2. Commit the change.
3. Re-run sync in consumer repos.

By default, the next sync removes stale managed files that:
- existed in the **previous lock file**
- are **not** present in the current manifest
- pass deletion safety checks

**Output examples:**
```text
REMOVED: docs/REFERENCE/OLD_GUIDE.md
SKIPPED REMOVAL (--no-delete): docs/REFERENCE/OLD_GUIDE.md
```

**Important safety rules:**
- If no previous lock exists (first-ever sync), no files are deleted.
- Only files listed in the **previous lock** are deletion candidates.
- User-created files that were never managed by sync are never touched.
- Unsafe stale paths (e.g., `../escape.txt`) are skipped with a security warning.
- Symlinked stale targets are skipped with a security warning instead of being deleted.

---
## Why Allow-List Instead of Exclusions
The previous approach used an `EXCLUDE_LIST` — everything in the repo was
synced *unless* it was in the exclusion list. This had several problems:
- New files added to tooling were silently synced to all consumers by default.
- There was no explicit record of what was intended to be synced.
- Forgetting to add a sensitive file to the exclusion list could accidentally
  propagate it to consumer repos.
The allow-list inverts this: you must **explicitly declare** that a file should
be synced. This is safer, more auditable, and easier to review in PRs.
---
## Consumer Project Identity Files (Never Synced)
The following files are deliberately **not** in the manifest and are never
synced. Each consumer project owns these files:
| File | Reason |
|------|--------|
| `VERSION` | Consumer manages its own release version |
| `pyproject.toml` | Generated per-project from `.pyproject.meta.toml` |
| `.pyproject.meta.toml` | Consumer-specific project identity |
| `tooling.toml` | Consumer-specific tooling config |
| `README.md` | Consumer writes its own README |
| `CHANGELOG.md` | Consumer maintains its own changelog |
| `requirements.txt` | Consumer manages app/runtime dependencies; no tooling-managed overlay/sections |
| `scripts/sync_tooling.sh` | Must be manually updated (bootstrap/security) |
| `project-template/` | Tooling-repo-only scaffolding |

`requirements-dev.txt` is part of the tooling-managed allow-list and is synced to
consumers as the shared dev-tooling dependency contract.
---
## Related
- `scripts/sync_tooling.sh` — the sync script that reads this manifest
- `scripts/validate_sync_drift.py` — validates managed files against the lock
- [`FILE_DISTRIBUTION.md`](../../FILE_DISTRIBUTION.md) — broader file ownership model
