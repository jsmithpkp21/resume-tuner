#!/usr/bin/env python3
"""Create GitHub issues for the sync-tooling hardening epic.

Creates one epic issue and five child issues that together deliver
deterministic, auditable tooling sync across all consumer repositories.

Usage:
    python3 scripts/create_sync_hardening_issues.py

Requirements:
    - GitHub CLI (gh) installed and authenticated
    - Run from the tooling repository root
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field


def _gh_preflight() -> None:
    """Verify `gh` is installed AND authenticated before any real
    invocation. Matches the AGENTS.md "Before using `gh` CLI in any
    script or make target, add `gh auth status` as an explicit
    preflight" guidance. A stale `GITHUB_TOKEN` env var silently
    overrides stored credentials and causes HTTP 401 — surfacing it
    here turns the failure into one actionable message instead of N
    opaque per-issue errors.
    """
    try:
        proc = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        sys.stderr.write(
            "create-sync-hardening-issues: `gh` CLI not found on PATH.\n"
            "Install with: https://cli.github.com/  (or your package manager).\n"
        )
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(
            "create-sync-hardening-issues: `gh auth status` failed; aborting.\n\n"
            f"{proc.stderr}\n"
            "Common causes: not logged in (run `gh auth login`), or a stale\n"
            "GITHUB_TOKEN env var overriding stored credentials.\n"
        )
        sys.exit(2)


COLLABORATION_CHECKLIST = """
## Working together checklist

- [ ] **1. Plan first** — ask Copilot for a plan in Plan mode; review and \
approve before any code is written
- [ ] **2. Scope it tight** — confirm this issue touches ≤ 1 script + tests \
+ docs before starting; resize if it feels too large
- [ ] **3. Implement** — switch to Agent mode; Copilot implements, runs \
`make check`, and validates before handing back
- [ ] **4. Review findings** — ask Copilot "review mindset: what could \
break?" before opening the PR
- [ ] **5. Commit and PR** — ask Copilot for a copy-ready conventional \
commit message and PR body linked to this issue number
"""


@dataclass
class Issue:
    """Specification for a single GitHub issue."""

    title: str
    body: str
    labels: list[str]
    issue_num: str | None = field(default=None, init=False)

    def create(self) -> str | None:
        """Create the issue via GitHub CLI and return the issue number."""
        try:
            result: subprocess.CompletedProcess[str] = subprocess.run(
                [
                    "gh",
                    "issue",
                    "create",
                    "--title",
                    self.title,
                    "--body",
                    self.body,
                    "--label",
                    ",".join(self.labels),
                ],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            url = result.stdout.strip()
            num = url.split("/")[-1] if "/" in url else None
            self.issue_num = num
            return num
        except subprocess.TimeoutExpired:
            print(
                f"❌ Timed out creating: {self.title}",
                file=sys.stderr,
            )
            return None
        except subprocess.CalledProcessError as exc:
            print(f"❌ Error creating issue: {exc.stderr}", file=sys.stderr)
            return None
        except FileNotFoundError:
            print(
                "❌ GitHub CLI (gh) not found. Install from https://cli.github.com/",
                file=sys.stderr,
            )
            sys.exit(1)


def _epic_body(child_placeholder: str) -> str:
    return f"""## Problem

The current sync system uses a hardcoded exclusion-list (`EXCLUDE_LIST`) inside
`scripts/sync_tooling.sh`. This model has three compounding failure modes:

1. **Silent over-sync** — any new file added to tooling is automatically pushed
   to all consumer repos unless someone remembers to add it to `EXCLUDE_LIST`.
2. **Stale file accumulation** — files removed from tooling stay in consumer
   repos indefinitely because there is no deletion step.
3. **No drift detection** — after a sync there is no ground truth to compare
   against, so manual edits to synced files go undetected until the next sync
   overwrites them (or doesn't).

`tooling.toml` also currently accepts `version = "main"` which means two syncs
run at different times can produce different results from the same config.

## Proposed Solution

Five focused changes, tracked as child issues:

| # | Child issue | One-line goal |
|---|-------------|---------------|
| 1 | Allow-list sync contract | Only sync explicitly listed files |
| 2 | Version pinning UX | Require tag/stable; persist resolved SHA |
| 3 | Drift manifest + checker | Write `.tooling-manifest.json`; add `make drift-check` |
| 4 | Safe deletion semantics | Remove no-longer-synced files during sync |
| 5 | `make update-sync-script` + docs/tests | Controlled update path for excluded script |

## Why Allow-List Over Exclusion-List

| Concern | Exclusion-list (current) | Allow-list (proposed) |
|---------|-------------------------|-----------------------|
| New file silently synced | Yes — default is sync | No — must be opted in |
| Stale file stays forever | Yes — no deletion trigger | Manifest detects orphans |
| Ground truth for drift | None | Manifest IS the answer |
| Removing deprecated files | Manual, easy to forget | Detected and automated |

## Out of Scope

- Full monorepo migration
- GitHub-only transport rewrite
- Backfilling historical manifests for past tags

## Acceptance Criteria

- [ ] Sync source of truth is an explicit allow-list, not implicit exclusion
- [ ] Sync requires or persists a deterministic tooling version (no floating default)
- [ ] `.tooling-manifest.json` is written after every sync and committed
- [ ] `make drift-check` exits non-zero when synced files have been locally modified
- [ ] Pre-commit push stage and CI both run drift check
- [ ] Files removed from allow-list are cleaned up during sync (with `--no-delete` opt-out)
- [ ] `make update-sync-script` provides a reviewed, auditable update path
- [ ] `FILE_DISTRIBUTION.md` and `PYPROJECT_ARCHITECTURE.md` reflect new contract
- [ ] Regression tests cover all new behaviours

## Child Issues

{child_placeholder}
{COLLABORATION_CHECKLIST}"""


def _child1_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Problem

`scripts/sync_tooling.sh` resolves sync candidates by taking every file in the
tooling repo and subtracting a hardcoded `EXCLUDE_LIST`. Any file added to
tooling is automatically synced to all consumer repos unless someone manually
adds it to the exclusion list. This is a silent over-sync risk with no
compile-time or test-time safety net.

## Current behaviour

`sync_tooling.sh` calls `git ls-tree` to enumerate all files, then skips
anything matching an entry in the hardcoded `EXCLUDE_LIST` array. The list is
maintained by subtraction — new files sync by default.

## Proposed behaviour

Add a `[sync]` section to `tooling/tooling.toml` that explicitly lists synced files:

```toml
[sync]
files = [
  "Makefile",
  "Dockerfile",
  "docker-compose.yml",
  "commitlint.config.mjs",
  "CONTRIBUTING.md",
  "CODING_STANDARDS.md",
  "DOCKER.md",
  "MANIFESTO.md",
  "FILE_DISTRIBUTION.md",
  ".pre-commit-config.yaml",
  "scripts/create_env.sh",
  "scripts/verify_env.sh",
  "scripts/merge_pyproject.py",
  "scripts/load_build_env.sh",
  "scripts/validate_activation_commands.py",
  "scripts/validate_version_sync.py",
  "scripts/__init__.py",
  "docs/REFERENCE/PYPROJECT_ARCHITECTURE.md",
]
```

Consumer projects can add a local `[sync].omit` list in their own `tooling.toml`
to skip files they do not need:

```toml
[sync]
omit = ["MANIFESTO.md"]
```

`sync_tooling.sh` reads the allow-list, applies any local `omit` entries, and
copies only the resolved set. The `EXCLUDE_LIST` is removed entirely.

## Risks and mitigations

**Risk:** Consumer repos that currently receive files not in the initial
allow-list will silently stop receiving them.
**Mitigation:** The initial allow-list is seeded from the current effective
sync set, so nothing is dropped on first use.

**Risk:** Tooling maintainer adds a file and forgets to add it to the allow-list.
**Mitigation:** Tests assert that every file in `[sync].files` actually exists
in the tooling repo at the synced ref.

## Acceptance Criteria

- [ ] `[sync].files` list exists in `tooling/tooling.toml`
- [ ] `scripts/sync_tooling.sh` only syncs files present in the allow-list
- [ ] `EXCLUDE_LIST` is fully removed from `sync_tooling.sh`
- [ ] Consumer `[sync].omit` entries are respected when present
- [ ] All existing path traversal and symlink safety checks are preserved
- [ ] A new file added to the tooling repo does NOT sync unless allow-listed
- [ ] Tests verify allow-list behaviour, omit override, and safety checks
{COLLABORATION_CHECKLIST}"""


def _child2_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Problem

`tooling.toml` currently accepts `version = "main"`. Two syncs run at different
times against `main` can produce different file contents, making sync
non-reproducible. There is also no record of when the last sync happened or
exactly which commit it came from.

## Proposed behaviour

**Version selection UX in `scripts/sync_tooling.sh`:**

| Input | Behaviour |
|-------|-----------|
| Tag e.g. `v1.7.4` | Sync at that exact tag; persist to `tooling.toml` |
| `stable` | Resolve latest tag on `release/stable`; persist resolved tag |
| `current` | Resolve HEAD SHA; persist SHA and nearest tag |
| Nothing provided | List available tags and exit with guidance — no silent default |

**`tooling.toml` additions written after sync:**

```toml
version        = "v1.7.4"     # user-chosen tag or keyword
locked_version = "v1.7.4"     # resolved tag
resolved_sha   = "abc1234..."  # exact commit SHA
synced_at      = "2026-03-11"  # ISO date
```

## Acceptance Criteria

- [ ] Running sync with no version argument prints available tags and exits non-zero
- [ ] `stable` resolves and persists the latest release tag
- [ ] `current` resolves HEAD to an immutable SHA and persists it
- [ ] An explicit tag syncs at exactly that ref and persists it
- [ ] `tooling.toml` contains `locked_version`, `resolved_sha`, and `synced_at` after sync
- [ ] Tests cover all four input modes including the no-arg guidance path
- [ ] Tests cover edge cases: no tags present, detached HEAD, unresolvable ref
{COLLABORATION_CHECKLIST}"""


def _child3_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Problem

After a sync there is no machine-readable record of what was copied, from what
version, or what the file contents were at sync time. This means:

- Local edits to synced files are invisible until the next sync.
- CI cannot enforce that synced files have not drifted.
- There is no basis for automated deletion (child issue 4).

## Proposed change

**`.tooling-manifest.json`** written after every sync:

```json
{{
  "tooling_version": "v1.7.4",
  "locked_sha": "abc1234...",
  "synced_at": "2026-03-11",
  "files": {{
    "Makefile": "sha256:aabbcc...",
    ".pre-commit-config.yaml": "sha256:ddeeff...",
    "scripts/create_env.sh": "sha256:112233..."
  }}
}}
```

**`scripts/check_tooling_drift.py`:**
- Reads `.tooling-manifest.json`
- Re-hashes every listed file using SHA-256 of file contents
- Reports `OK`, `DRIFT`, or `MISSING` per file
- Exits non-zero on any drift or missing file

**`make drift-check`** target in `Makefile`.

**Pre-commit push hook** — `tooling-drift-check` (push stage only, not every commit).

**CI step** in `verify-environment.yml`.

## Acceptance Criteria

- [ ] `.tooling-manifest.json` is written after every sync
- [ ] Manifest contains version, SHA, date, and per-file SHA-256 hashes
- [ ] `make drift-check` exits 0 on clean state, non-zero on any drift
- [ ] `check_tooling_drift.py` reports `DRIFT`/`MISSING`/`OK` per file
- [ ] Pre-commit push hook runs drift check
- [ ] CI `verify-environment` job runs drift check and fails the build on drift
- [ ] Tests cover: clean state, one drifted file, one missing file, missing manifest
{COLLABORATION_CHECKLIST}"""


def _child4_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Dependencies

Requires child issues for allow-list (issue 1 in epic) and manifest (issue 3
in epic) to be merged first.

## Problem

When a file is removed from the tooling allow-list or deleted from the tooling
repo at the target version, the stale copy stays in consumer repos indefinitely.
There is currently no mechanism to detect or clean these orphaned files up.

## Proposed change

At the end of `scripts/sync_tooling.sh`, after copying new files:

1. Load `.tooling-manifest.json` from the **previous** sync (if present).
2. Identify files in the previous manifest that are **not** in the current
   allow-list or no longer exist in the tooling repo at the target ref.
3. Print a `REMOVED:` line for each orphaned file.
4. Delete them from the consumer repo (default).
5. Skip deletion when `--no-delete` flag is passed; print an advisory instead.

**Example output:**
```
REMOVED: docs/REFERENCE/OLD_GUIDE.md (no longer in tooling allow-list)
REMOVED: scripts/legacy_helper.py (deleted from tooling at v1.8.0)
```

## Safety constraints

- If no previous manifest exists (first-ever sync), no files are deleted.
- Only files that appear in the **previous** manifest are candidates for deletion;
  files that were never synced are never touched.

## Acceptance Criteria

- [ ] Files in the previous manifest but absent from the current allow-list are detected
- [ ] Detected orphans are deleted by default
- [ ] `--no-delete` suppresses deletion and prints an advisory
- [ ] Removal report is printed regardless of `--no-delete`
- [ ] First-ever sync (no previous manifest) never deletes anything
- [ ] Tests cover: normal deletion, `--no-delete`, no previous manifest
- [ ] `FILE_DISTRIBUTION.md` documents deletion behaviour and opt-out
{COLLABORATION_CHECKLIST}"""


def _child5_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Dependencies

Best run after child issues 1–4 are merged, but docs and test scaffolding
can start in parallel.

## Problem

`scripts/sync_tooling.sh` is intentionally excluded from auto-sync for security
reasons. When it is updated in tooling, consumer repos have no guided update
path — maintainers must manually diff and copy, or silently stay on an old
version. This is easy to forget and produces no audit trail.

Additionally, `FILE_DISTRIBUTION.md` and `PYPROJECT_ARCHITECTURE.md` do not
yet describe the allow-list, manifest, or drift-check contract introduced by
child issues 1–4.

## Proposed change

**`make update-sync-script` in `Makefile`:**

1. Locate the tooling repo (same resolution order as sync).
2. Show a diff summary of local vs tooling `scripts/sync_tooling.sh`.
3. Require the user to type `yes` to confirm.
4. On confirmation: copy the file and print the resolved tooling version it came from.

**Docs updates:**

- `FILE_DISTRIBUTION.md` — document allow-list model, manifest, deletion
  behaviour, version pinning, and `update-sync-script` update path.
- `docs/REFERENCE/PYPROJECT_ARCHITECTURE.md` — update Sync Governance section
  to reflect deterministic versioning and drift-check contract.

**Test updates:**

- `tests/scripts/test_sync_tooling_regressions.py` — add assertions covering
  allow-list, version-lock, manifest, and deletion behaviours end-to-end.
- `tests/scripts/test_tooling_drift.py` — full coverage: clean, drifted,
  missing, and no-manifest cases.

## Acceptance Criteria

- [ ] `make update-sync-script` shows a diff summary before acting
- [ ] Copy is performed only after explicit `yes` confirmation
- [ ] Tooling version the script came from is printed on copy
- [ ] `FILE_DISTRIBUTION.md` covers all new sync contract concepts end-to-end
- [ ] `PYPROJECT_ARCHITECTURE.md` Sync Governance section matches new contract
- [ ] Regression tests cover behaviours introduced in child issues 1–4
- [ ] All checks pass: `make check`, `make drift-check`, `make version-check`
- [ ] `update-sync-script` handles missing tooling repo gracefully with a clear error
{COLLABORATION_CHECKLIST}"""


def _template_issue_body(epic_num: str) -> str:
    return f"""## Parent epic

Part of #{epic_num}

## Problem

The tooling repository has four issue templates (`bug_report`, `feature_request`,
`documentation`, `update_projects_beta`) but is missing templates for two common
issue types used in this project:

1. **Epic** — umbrella tracking issue for a group of related child issues
2. **Refactor** — restructuring existing code without changing observable behaviour

Additionally:

- `.github/PULL_REQUEST_TEMPLATE.md` does not exist at the repository root
  (there is a copy under `docs/REFERENCE/` which GitHub does not use).
- `config.yml` references `base_repo` security policy URL instead of `tooling`.

## Proposed change

- Add `.github/ISSUE_TEMPLATE/epic.yml`
- Add `.github/ISSUE_TEMPLATE/refactor.yml`
- Add `.github/PULL_REQUEST_TEMPLATE.md` (move from `docs/REFERENCE/`)
- Fix security policy URL in `config.yml`

All new templates include the five-step collaboration checklist as a pre-filled
textarea so every issue and PR carries the working workflow by default.

## Acceptance Criteria

- [ ] `epic.yml` template appears in GitHub "New issue" picker
- [ ] `refactor.yml` template appears in GitHub "New issue" picker
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` is used by GitHub when opening PRs
- [ ] Security policy URL in `config.yml` points to the `tooling` repo
- [ ] All template YAML passes `pre-commit run check-yaml`
{COLLABORATION_CHECKLIST}"""


def _projects_body(epic_num: str) -> str:
    return f"""## Parent epic

Follow-up to #{epic_num}

## Problem

The sync-hardening epic will produce 5–6 child issues worked through sequentially.
Without a visual board it is hard to see at a glance which issues are todo,
in progress, blocked, or done — especially when picking up work after a break.

## Proposed change

Create a GitHub Projects (beta) board for the tooling repository with:

**Columns:**
- `Todo` — issue created, not yet started
- `In Progress` — branch opened or work actively underway
- `In Review` — PR open, waiting for review or checks
- `Done` — PR merged, issue closed

**Automation rules:**
- Issue opened → move to `Todo`
- PR opened and linked to issue → move to `In Progress`
- PR merged → move to `Done` and close linked issue
- Issue closed manually → move to `Done`

**Initial population:**
Add all issues from the sync-hardening epic (#{epic_num} and children) to the
board on creation.

**Label automation (optional stretch goal):**
- Add `in-progress` label when card moves to `In Progress` column
- Remove `in-progress` label when card moves to `Done`

## Why not a monorepo

GitHub Projects is orthogonal to the multi-repo layout. It is a visualization
layer on top of issues and PRs and does not change how we write issues, work
through the 5-step checklist, or structure PRs.

## Acceptance Criteria

- [ ] GitHub Projects board exists for the `tooling` repository
- [ ] Columns: Todo, In Progress, In Review, Done
- [ ] Automation: issue opened → Todo; PR opened → In Progress; PR merged → Done
- [ ] All sync-hardening epic issues added to the board
- [ ] `CONTRIBUTING.md` documents the board URL and column workflow
- [ ] Board URL added to this issue as a comment after creation
{COLLABORATION_CHECKLIST}"""


def get_issues() -> tuple[Issue, list[Issue]]:
    """Build the epic and child issue objects (without real issue numbers yet)."""
    child1 = Issue(
        title="refactor(sync): replace exclusion-list with explicit allow-list in tooling.toml",
        body="",  # filled after epic number is known
        labels=["refactor", "tooling", "scripts", "architecture"],
    )
    child2 = Issue(
        title="feat(sync): require deterministic tooling version and persist lock metadata",
        body="",
        labels=["enhancement", "tooling", "scripts", "ci-cd"],
    )
    child3 = Issue(
        title="feat(sync): write sync manifest and add drift checker",
        body="",
        labels=["enhancement", "tooling", "scripts", "ci-cd"],
    )
    child4 = Issue(
        title="feat(sync): safe deletion of files removed from allow-list",
        body="",
        labels=["enhancement", "tooling", "scripts"],
    )
    child5 = Issue(
        title="feat(sync): add make update-sync-script and align docs and tests",
        body="",
        labels=["enhancement", "tooling", "makefile", "documentation", "ci-cd"],
    )

    child6 = Issue(
        title="chore(projects): set up GitHub Projects board for sync-hardening epic",
        body="",
        labels=["chore", "github-projects", "tooling"],
    )

    epic = Issue(
        title="epic(sync): harden sync-tooling to eliminate cross-repo drift",
        body="",  # filled after child numbers are known
        labels=["epic", "architecture", "tooling", "scripts", "ci-cd", "high-priority"],
    )

    return epic, [child1, child2, child3, child4, child5, child6]


def main() -> None:
    """Create the template issue, epic, and all child issues."""
    _gh_preflight()

    print("Creating sync-tooling hardening issues...")
    print("=" * 60)

    epic, children = get_issues()
    total_steps = 1 + len(children)

    # Step 1: create template issue first (no epic dependency)
    print(f"\n[0/{total_steps}] Creating template/infrastructure issue...")
    template_issue = Issue(
        title="chore(templates): add epic and refactor issue templates and fix PR template",
        body=_template_issue_body("TBD"),
        labels=["chore", "documentation"],
    )
    template_num = template_issue.create()
    if template_num:
        print(f"  ✓ Template issue created: #{template_num}")
    else:
        print("  ⚠ Template issue creation failed — continuing")
        template_num = "TBD"

    # Step 2: create epic (child numbers not yet known — use placeholders)
    print(f"\n[1/{total_steps}] Creating epic issue...")
    placeholder_children = "\n".join(
        [f"- [ ] #TBD — {child.title}" for child in children]
    )
    epic.body = _epic_body(placeholder_children)
    epic_num = epic.create()
    if not epic_num:
        print("❌ Epic creation failed. Aborting.", file=sys.stderr)
        sys.exit(1)
    print(f"  ✓ Epic created: #{epic_num}")

    # Step 3: create children with real epic number
    body_fns = [
        _child1_body,
        _child2_body,
        _child3_body,
        _child4_body,
        _child5_body,
        _projects_body,
    ]
    for i, (child, body_fn) in enumerate(zip(children, body_fns, strict=True), start=2):
        print(f"\n[{i}/{total_steps}] Creating child issue: {child.title[:60]}...")
        child.body = body_fn(epic_num)
        num = child.create()
        if num:
            print(f"  ✓ Created: #{num}")
        else:
            print(f"  ⚠ Failed to create: {child.title}")

    # Step 4: update epic with real child issue numbers
    child_nums = [c.issue_num for c in children]
    if all(child_nums):
        child_titles = [
            "Allow-list sync contract",
            "Version pinning UX",
            "Drift manifest and checker",
            "Safe deletion semantics",
            "make update-sync-script and docs/tests",
            "GitHub Projects board (follow-up)",
        ]
        real_children = "\n".join(
            [f"- [ ] #{n} — {t}" for n, t in zip(child_nums, child_titles, strict=True)]
        )
        updated_body = _epic_body(real_children)
        try:
            subprocess.run(
                ["gh", "issue", "edit", epic_num, "--body", updated_body],
                check=True,
                timeout=30,
                capture_output=True,
            )
            print(f"\n✓ Epic #{epic_num} updated with real child issue numbers.")
        except subprocess.CalledProcessError as exc:
            print(f"\n⚠ Could not update epic body: {exc.stderr}", file=sys.stderr)

    # Summary
    print("\n" + "=" * 60)
    print("Done. Issues created:")
    if template_num != "TBD":
        print(f"  Template: #{template_num}")
    print(f"  Epic:     #{epic_num}")
    for child in children:
        status = f"#{child.issue_num}" if child.issue_num else "FAILED"
        print(f"  Child:    {status} — {child.title[:55]}")
    print("\nNext step: open the epic on GitHub and verify child links.")
    print(f"  https://github.com/jsmithpkp21/tooling/issues/{epic_num}")


if __name__ == "__main__":
    main()
