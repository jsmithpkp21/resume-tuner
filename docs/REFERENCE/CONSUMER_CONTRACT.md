# Consumer Contract Gate

This document describes the consumer contract CI gate that runs in tooling CI to
prove that core consumer flows remain stable before merge.

## What it validates

The gate exercises the following contracts using a **resume-builder-compatible
fixture profile** as the reference consumer:

| Contract area | What is tested |
|---|---|
| **Sync apply + lock** | Managed files are copied; lock is written with correct SHA-256 entries |
| **Drift-check enforcement** | Drift validator passes after a clean sync; fails on modification, deletion, or missing lock |
| **Env lifecycle verification** | `verify_env.sh` reads all required config files (VERSION, tooling.toml) and prints expected metadata values; the only permitted failure is a missing venv, not absent files |

---

## Local run path

Run the contract tests directly from the repository root:

```bash
pytest -q tests/scripts/test_consumer_contract.py
```

Or run together with the full regression suite:

```bash
pytest -q tests/scripts/test_sync_tooling_regressions.py \
          tests/workflows/test_build_inputs_integration.py \
          tests/scripts/test_consumer_contract.py
```

Or via the standard make target (picks up all tests automatically):

```bash
make test
```

---

## CI gate

The `consumer-contract` job in `.github/workflows/verify-environment.yml` runs
`pytest -q tests/scripts/test_consumer_contract.py` inside the project Docker
image and is a **required** gate for CI to pass (the `status` job depends on it).

A failure in this job means at least one of the following consumer contracts is
broken:

- Sync did not produce the expected files or lock
- Drift validator returned the wrong exit code
- `verify_env.sh` failed pre-flight (missing required files) or reported an unexpected error

---

## Fixture profile

The resume-builder fixture is defined in `_make_resume_builder_consumer()` inside
`tests/scripts/test_consumer_contract.py`. It creates a temporary directory with:

- `tooling.toml` — Python 3.11 + pip version declaration
- `.pyproject.meta.toml` — resume-builder project identity
- `VERSION` — semver project version
- `pyproject.toml` — minimal PEP 621 metadata
- `requirements.txt` — minimal dependency list

To add a second consumer profile, duplicate the fixture helper with the new
project's identity files and parameterize or copy the relevant test functions.

---

## See also

- `scripts/sync_tooling.sh` — managed-file sync implementation
- `scripts/validate_sync_drift.py` — drift validator
- `scripts/verify_env.sh` — environment verification script
- `docs/REFERENCE/SYNC_MANIFEST.md` — full sync contract documentation
- `tests/scripts/test_sync_tooling_regressions.py` — lower-level sync regression tests
