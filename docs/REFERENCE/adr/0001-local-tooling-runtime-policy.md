# ADR-0001: Local tooling runtime policy — local-first with Docker fallback

- Status: Accepted
- Date: 2026-04-30
- Deciders: tooling maintainers (issue #155)
- Related: #118 (commitlint runtime hardening — consistent with this policy)

## Context

This repo family (tooling + synced consumers) emphasizes deterministic
development environments and reproducible automation. Several developer-tooling
workflows already exist that need a non-Python runtime (Node for `markdownlint`,
`commitlint`, etc.).

Two patterns exist in the wild:

- **Local-first with Docker fallback.** Try a pinned local binary or
  package-manager install; fall back to a pinned Docker image if the local
  runtime is unavailable; hard-fail with actionable remediation if neither path
  works. This is what the `markdown-lint-run` target and
  `scripts/run_commitlint.sh` already do.
- **Docker-first by default.** Always invoke through a pinned Docker image and
  treat the local binary as the exception.

A separate, fully containerized track also exists via the `docker-up`,
`lint-docker`, `test-docker`, and `check-docker` make targets, with
`DOCKER.md` documenting the flow as a first-class option.

Issue #155 asks whether local tooling defaults should flip to Docker-first.

## Decision

Adopt **local-runtime-first with Docker-fallback** as the documented policy for
local developer tooling. Keep the parallel **`*-docker` make targets** as the
supported opt-in for users who want a fully containerized substrate. **Reject
Docker-first-by-default.**

Any local-first tool that follows this policy MUST satisfy the invariants in
the next section. Tools that cannot satisfy them MAY opt out under the
exception policy.

## Required invariants

Every script that resolves between a local runtime and a Docker fallback must:

1. **Pin the runtime version.** Hard-coded constant in the script
   (e.g. `COMMITLINT_VERSION="19.8.0"`).
2. **Pin the Docker image.** Specific tag (`node:20-bullseye`), never a
   floating tag like `node:latest`.
3. **Harden install paths.** All package-manager invocations on both local and
   Docker paths use `--ignore-scripts --no-audit --no-fund` (npm) or
   equivalent. Established by #118.
4. **Distinguish runtime-setup failure from validation failure.** Use a
   sentinel exit code (e.g. `INSTALL_FAIL_RC=125`) so a real validation
   rejection from the local runtime is never silently retried under Docker.
5. **Hard-fail with actionable remediation** when both runtimes are
   unavailable. Existing scripts already do this; new ones must too.
6. **Cache install artifacts** when on a hot path
   (`$XDG_CACHE_HOME/tooling-<tool>/<version>/`).

## Exception policy

A tool MAY opt out of local-first and require Docker if **all** of the
following hold:

- Pinning the local runtime is impractical or insecure (e.g., a compiled binary
  with no reproducible distribution).
- The workflow is not on the commit-time / pre-commit hot path.
- A documented `*-docker` invocation already exists or ships with the change.

Any opt-out must be called out in the script header and in
`docs/REFERENCE/PRE_COMMIT_HOOKS.md`.

## Consequences

- **Latency:** unchanged for default users; commit-msg stays sub-second after
  first install.
- **Reliability:** unchanged; existing fallback semantics retained. Daemon
  health remains a fallback-path concern, not a hot-path concern.
- **Onboarding:** improved — the policy is now written down once and referenced
  from `AGENTS.md`, `PRE_COMMIT_HOOKS.md`, and `DOCKER.md`.
- **Supply chain:** the `--ignore-scripts --no-audit --no-fund` invariant
  generalizes the #118 hardening to every future tool that joins this family.
- **Determinism contract:** CI remains the binding determinism contract; local
  tooling is a fast feedback loop, not a parity oracle.

## Alternatives considered

- **Docker-first default.** Rejected. The supply-chain argument that usually
  motivates it is already neutralized by the #118 hardening, while the latency
  and WSL2 daemon-health costs hit the commit-time hot path directly.
- **Configurable per-invocation (env var / flag) as the default.** Rejected as
  a default — adds cognitive load without solving a real problem. Individual
  scripts MAY expose a `FORCE_DOCKER=1`-style override if a concrete use case
  appears.

## Enforcement / documentation touchpoints

- `AGENTS.md` — short "Local tooling runtime policy" section pointing here.
- `docs/REFERENCE/PRE_COMMIT_HOOKS.md` §7 — cross-link this ADR.
- `DOCKER.md` — cross-link as the explicit Docker track.
- Optional follow-up: structural test asserting that any `scripts/*.sh` which
  shells out to `docker` also implements the local-first resolution and
  sentinel pattern. Filed as a follow-up issue rather than blocking this ADR.

## Follow-ups

1. Cross-link this ADR from `AGENTS.md`, `PRE_COMMIT_HOOKS.md`, and
   `DOCKER.md`.
2. Optional structural lint for the resolution-order + sentinel pattern (new
   issue, gated on whether more tools join the family).
3. Back-link comment on #118 once #155 closes, noting consistency with this
   policy.
