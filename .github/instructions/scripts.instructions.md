---
applyTo: "scripts/sync_tooling.sh"
---

# `scripts/sync_tooling.sh` — Critical Invariants

This script is the entry point for managed-file sync into consumer repos. It
runs with the trust of the consumer repo's local checkout and writes into
that consumer's working tree. Treat changes here as security-sensitive and
preserve every invariant below; add tests for any behavior change.

## Security invariants you must preserve

- **Path traversal protection (`validate_sync_path` + `normalize_sync_path`).**
  Manifest paths must be repo-relative POSIX paths. The script rejects any
  path that begins with `/` (absolute) or contains `..` segments, then
  normalizes the remainder and rejects any normalized path whose
  `os.path.commonpath` with `TARGET_DIR_ABS` is not `TARGET_DIR_ABS` itself
  (i.e. anything that would escape the consumer repo). Do not weaken these
  three checks — they are the trust boundary that prevents a malicious
  manifest entry from writing outside the consumer tree.
- **Symlink protection (`validate_no_symlink_traversal`).** Reject any
  destination path where the destination itself, or any parent component
  under `TARGET_DIR_ABS`, is a symlink. The check is unconditional — there
  is no "replace symlink" branch and you should not add one. Stale-file
  removal must also short-circuit on symlinked targets (see the
  `SECURITY: Skipping stale file removal because target is symlink` path).
- **Fail-closed behavior.** If the manifest is missing or malformed, abort
  immediately with a non-zero exit; do not synthesize defaults. If a declared
  path does not exist in the tooling source at the requested version, abort.
- **Sync source mode contract.** Three modes exist: `filesystem` (sync from
  a local archive directory), `git` (sync from a local sibling checkout —
  the default everyone actually uses), and a GitHub-remote mode that is
  *not yet implemented* and intentionally `exit 1`s with a remediation
  message. `git` mode is supported and required for normal use; do not
  conflate it with the unimplemented remote mode. If you wire up the
  remote mode, ship it with a threat model, signature/ref pinning, and
  tests — the current fail-fast guard is what keeps unsigned remote pulls
  from silently happening today.
- **Lock file is authoritative.** `.tooling-sync-manifest.lock` records what
  was actually applied. Do not skip writing it on success, and do not trust
  unsigned hashes. Refuse to write the lock when the lock path itself, or
  any managed file, is a symlink.
- **Stale-file deletion is opt-out, not opt-in.** Removing a path from the
  manifest must delete the consumer copy on the next sync (governed by
  `--no-delete` / `SYNC_NO_DELETE`). Preserve this default.

## Required co-changes when scope changes

If you add, remove, or rename a managed file, you must also update:

- `.tooling-sync-manifest.toml` (in the tooling source repo only)
- `FILE_DISTRIBUTION.md`
- `tests/scripts/test_sync_tooling_regressions.py`
- `docs/REFERENCE/SYNC_MANIFEST.md` if the schema or contract changes

## Validation before requesting review

Run, in this order, and resolve every failure:

```bash
make lint
pytest -q tests/scripts/test_sync_tooling_regressions.py
make drift-check
make agents-drift-check
```

If you cannot reproduce a CI failure locally, do not paper over it — the
sync contract is the trust boundary for every consumer repo.
