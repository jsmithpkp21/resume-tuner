# Performance Baseline & Slow-Test Convention

This document captures the performance baseline for local pre-commit hooks and
`pytest` runs, and codifies the `@pytest.mark.slow` convention that selective
test execution (epic #116) is built on. Update the **Baseline** section
whenever a perf-affecting change lands.

## Baseline (measured 2026-04-29 against tooling 1.17.x + the 307-test suite)

### Local pre-commit (`pre-commit run --hook-stage commit --all-files`)

| Stage          | Pre-#122 | Post-#122 | Reduction |
|----------------|----------|-----------|-----------|
| commit (all)   | ~24s     | ~2s       | ~92%      |

Phase 2 (#122) moved `pytest-check` from `[commit, push]` to `[push]`. The
full `pytest -q` suite was the dominant cost (~19s of the ~24s commit-stage
wall-clock); CI's `make test` and the push-stage hook remain the safety
nets for full-suite regressions.

### Full `pytest -q --durations=10`

| Metric         | Value      |
|----------------|------------|
| Test count     | 307        |
| Total wall-clock | ~19s     |

### Slowest tests (top 5 from `--durations=25`)

| Test                                                                                       | Time   |
|--------------------------------------------------------------------------------------------|--------|
| `test_precommit_drift_e2e.test_prepush_drift_hook_fails_when_lock_missing`                 | 3.26s  |
| `test_precommit_drift_e2e.test_prepush_drift_hook_passes_for_clean_managed_state`          | 3.20s  |
| `test_consumer_contract.test_consumer_real_manifest_sync_includes_shared_dev_requirements` | 2.01s  |
| `test_consumer_contract.test_consumer_real_manifest_sync_applies_all_declared_files`       | 1.98s  |
| `test_commitlint_local_parity.test_valid_commit_passes`                                    | 0.32s  |

These nine tests (the four named above plus the four other commitlint parity
tests) are marked `@pytest.mark.slow` and account for roughly half the total
runtime. They spawn real subprocesses (pre-commit, npm, bash) and are
inherently process-bound.

### Measured slow vs fast split (2026-04-29)

| Selector              | Tests executed\* | Wall-clock |
|-----------------------|------------------|------------|
| Default (full suite)  | 307              | ~19s       |
| `-m 'not slow'` (fast)| 298              | ~7s        |
| `-m slow` (slow only) | 9                | ~2s        |

\* All three rows collect the full 307 tests — `-m` only filters which
ones execute. `298 + 9 = 307`.

The fast subset is what selective execution (#123) and the CI test split
(#124) target. Note that as more fast (logic-only) tests are added, the
absolute slow/fast ratio shrinks; the convention's value is profiling
clarity and CI-split prep, not just raw speedup.

## Pre-commit stage policy (Phase 2 / #122)

Pre-commit hooks split into three buckets. Future hook additions should pick
the cheapest bucket that still preserves the gate's intent.

### Commit stage (must stay fast — runs on every `git commit`)

| Hook                       | Why it stays cheap                                            |
|----------------------------|---------------------------------------------------------------|
| `ruff` (default)           | Default `pass_filenames: true` — only diffs the changed files |
| `ruff-format` (default)    | Same — changed-file scope                                     |
| `mypy` (default)           | Same — changed-file scope                                     |
| `version-sync-check`       | Single Python script reading 4 files; <100 ms                 |
| `env-file-check`           | Same idiom; skips cleanly when `.env` or `tooling.toml` is absent |
| `markdown-lint`            | Local `markdownlint` binary first, Docker fallback only when needed |
| `workflow-action-pin-fix`  | Auto-fixes pin drift in seconds                               |
| File-format checks         | `check-yaml` / `check-toml` / `check-json` / etc. — milliseconds |

### Push stage (full safety net before remote)

| Hook                          | Why push-only                                              |
|-------------------------------|------------------------------------------------------------|
| `pytest-check`                | Selective runner (#123) — narrow path ~2s, full fallback ~15s |
| `ruff-check-all`              | Whole-repo ruff (`args: ["."]`, `pass_filenames: false`)   |
| `ruff-format-check-all`       | Whole-repo format check                                    |
| `mypy-check-all`              | Whole-repo type check                                      |
| `tooling-drift-check`         | Exercises sync state; only meaningful before publishing    |
| `workflow-action-pin-check`   | Whole-tree workflow scan                                   |

### CI

CI runs the test suite split into two parallel jobs (Phase 4 / #124):

- **`Run Tests (fast)`** — `make test-fast` →
  `pytest -q --durations=10 -m 'not slow'` (~298 tests, the logic-only
  majority).
- **`Run Tests (slow)`** — `make test-slow` →
  `pytest -q --durations=10 -m slow` (~9 tests that spawn real
  subprocesses).

Both targets keep `--durations=10` so each CI job emits its own
top-10-slowest table for profiling.

Both depend on `Build Docker Image` (which produces the cached image
artifact) and run in parallel. The `CI Status` aggregator depends on
both, so branch protection covers the full test surface.

Local `make test` still runs the entire suite as the simplest entry point
for "run everything"; CI's `make test-fast` + `make test-slow` is a
parallel decomposition, not a different test set.

The CI split is locked structurally by
`tests/scripts/test_precommit_quality_gate.py::test_ci_test_job_split_into_fast_and_slow_parallel_jobs`
(asserts both jobs exist, depend on `build`, invoke the matching `make`
target, and that the status aggregator's `needs:` list AND its inline
script reference both `test-fast` and `test-slow`) plus
`test_makefile_test_fast_and_test_slow_targets_use_marker_split` (locks
the marker selectors). The Phase 2 stage policy is locked separately by
`test_stage_policy_locks_phase2_split_between_commit_and_push`.

## Selective pytest execution (Phase 3 / #123)

The push-stage `pytest-check` hook now invokes `scripts/run_pytest_selective.py`
instead of the bare `pytest -q`. The script maps changed files (computed from
`git diff @{upstream}..HEAD` when an upstream is tracked, or from
`<merge-base>..HEAD` against the default remote branch — `origin/HEAD`,
falling back to `origin/main` then `origin/master` — when no upstream is
set yet) to relevant test paths, falling back to the full suite when:

- Any changed file is in the **infra** set (`Makefile`, `pyproject.toml`,
  `Dockerfile`, `docker-compose.yml`, `requirements*.txt`,
  `.pre-commit-config.yaml`, `.tooling-sync-manifest.toml`, `tooling.toml`,
  `.env`, `VERSION`, `.github/workflows/**`, `project-template/**`).
- More than 10 files changed.
- Any changed file is unmapped (safe default — never skip tests for unknown
  paths).

**Always-run guards** (cheap structural / convention checks) run regardless
of selection — but only the ones that exist in the consuming repo. The
script defines three candidate guards and filters to the subset present
on disk:

| Candidate guard                                  | In tooling | Synced to consumers |
|--------------------------------------------------|------------|---------------------|
| `tests/scripts/test_consumer_contract.py`        | ✅ | ✅ |
| `tests/scripts/test_pytest_markers.py`           | ✅ | ❌ (tooling-internal) |
| `tests/scripts/test_precommit_quality_gate.py`   | ✅ | ❌ (tooling-internal) |

Tooling runs all three; consumers run only the contract test. The two
tooling-internal guards assert tooling-source-repo conventions (the
`slow` marker registry and the pre-commit stage policy) that don't
apply to consumers, so they're intentionally not synced.

### Default mapping rule

`scripts/<x>.py` or `scripts/<x>.sh` → `tests/scripts/test_<x>.py` (verified
to exist; missing test file falls back to full). Test-file changes run that
file. Explicit-mapping overrides live in
`scripts/run_pytest_selective.py::EXPLICIT_MAPPINGS` for non-derivable cases
(e.g. `commitlint.config.mjs` → `test_commitlint_local_parity.py`).

### Adding a new mapping

1. If the natural rule already covers it (`scripts/foo.py` →
   `tests/scripts/test_foo.py`), no action needed.
2. Otherwise add an entry to `EXPLICIT_MAPPINGS` and a unit test in
   `tests/scripts/test_run_pytest_selective.py` exercising the new path.
3. Re-measure: a representative narrow change should still complete well
   under the full-suite time, and the full fallback should remain unchanged.

### Measured deltas (2026-04-29 against tooling 1.17.x + the 307-test suite)

| Change class                           | Tests run | Wall-clock | vs full |
|----------------------------------------|-----------|------------|---------|
| Single mapped script (`validate_env_file.py`) | 40 (incl. guards) | ~1.5s | ~10% |
| Infra fallback (`Makefile`)            | 307       | ~14.6s     | 100%    |

CI (`make test`) is unchanged — it runs the full suite as the final safety
net, so any selector miss is caught at PR-time before merge.

## `slow` marker convention

A test should be marked `@pytest.mark.slow` if any of the following is true:

- It spawns a real subprocess (pre-commit, npm, bash, docker) per assertion.
- It hits the filesystem heavily (initializes a git repo, writes many files).
- Its individual wall-clock exceeds ~0.5s on the reference machine.

Plain logic / parser / structural-assertion tests should remain unmarked.

### Running with / without slow tests

```bash
# Default: run everything (CI behavior)
pytest -q

# Fast iteration: skip slow tests
pytest -q -m 'not slow'

# Profile only the slow inventory
pytest -v -m slow
```

### Profiling target

For ad-hoc deep dives, use:

```bash
make test-profile
```

This runs `pytest -v --durations=20 --tb=no` against the live env. Prefer
plain `make test` for normal runs (which already passes `--durations=10`).

## Regression policy

A regression is recorded when **any** of the following holds across three
consecutive `make test` runs on `main`:

- Total wall-clock > 25s (current baseline ~19s; +30% margin).
- The slowest single test exceeds 6s (current ceiling ~3.3s; +80% margin).
- A previously-fast test (under 0.5s) now exceeds 1s.

When a regression is detected, file an issue under epic #116 with the
`pytest --durations=25 --tb=no` output attached and link the offending
commit/PR.

## Related issues

- Epic #116 — Speed up pre-commit and CI feedback loop
- #121 — Phase 1: Baseline tooling and profiling infrastructure (this doc)
- #122 — Phase 2: Local hook staging and quick wins
- #123 — Phase 3: Selective pytest execution by changed files
- #124 — Phase 4: CI optimization and structural hardening
