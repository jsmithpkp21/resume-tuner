# CONTEXT.md — resume-builder repo

> Committed baseline. Update when architecture changes.
> Branch/session overrides go in `CONTEXT_LOCAL.md` (gitignored).

## Repo Role

Consumer of `tooling` sync. Builds AI-assisted resume generation tooling.
Receives managed files via `sync_tooling.sh` from sibling `../tooling` checkout.

## High-Value Files (read before editing core logic)

| File | Why |
|---|---|
| `Makefile` | All make targets |
| `scripts/sync_tooling.sh` | Managed by tooling sync; do not hand-edit |
| `.pyproject.meta.toml` | Consumer identity input for `pyproject.toml` generation |
| `data/` | Resume source data (manifests, experience, profile, skills) |
| `tests/scripts/test_consumer_contract.py` | Contract tests |

## Generated — Do Not Edit Directly

- `pyproject.toml` — generated via `scripts/merge_pyproject.py` + `.pyproject.meta.toml`
- `.tooling-sync-manifest.lock` — written by sync script

## Invariants to Preserve

- `pyproject.toml` must be regenerated via script, never hand-edited
- `AGENTS_LOCAL.md` must stay out of tooling-managed sync/manifest state so local guidance is never overwritten by sync
- `CONTEXT_LOCAL.md` must stay out of tooling-managed sync/manifest state and is gitignored — create locally per branch/session
- GitHub Actions must use strict `@vX.Y.Z` pins
- Conventional commits enforced via `scripts/run_commitlint.sh`
- `.tooling-sync-manifest.toml` (source of truth) is in the tooling repo, not synced to consumers

## Scope Boundaries

- App-specific changes stay in `resume-builder` only
- Shared tooling fixes go to `tooling` repo first, then sync to consumers
- Do not push consumer identity files back to tooling

## Key Check Commands

```bash
make lint
make test
make check
make drift-check
pytest -q tests/scripts/test_consumer_contract.py
```
