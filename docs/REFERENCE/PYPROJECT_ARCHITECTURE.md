# pyproject.toml Architecture

## Problem
Previously, consumer project `pyproject.toml` files were synced directly from the tooling repository. This caused project-specific metadata (for example `name` and `version`) to be overwritten on sync and drift from each project's own release/version metadata.

Additionally, there was significant duplication: every project carried many lines of identical tool configuration.

## Solution
**Dynamic generation via metadata merging.**

Instead of syncing `pyproject.toml` directly, projects store only metadata in `.pyproject.meta.toml`, and `sync_tooling.sh` merges it with `tooling/pyproject.toml` to generate the final `pyproject.toml`.

### Files and Workflow

#### `tooling/pyproject.toml`
- **Purpose**: Shared build system and tool configurations
- **Contents**:
  - `[build-system]` - standard build backend
  - `[tool.*]` - configurations for black, ruff, isort, mypy, pytest
- **Synced**: **No** — lives only in tooling; used by merge script as template
- **Updated by**: Tooling maintainers when tool configs need adjustment

#### `.pyproject.meta.toml` (in each project)
- **Purpose**: Project-specific metadata only
- **Contents**:
  - `[project]` - name, version, description, authors
  - Optional `[tool.*]` - project-specific tool overrides (merged with tooling configs)
- **Synced**: **No** — intentionally excluded from sync to preserve each project's identity
- **Updated by**: Project maintainers, kept in version control
- **Bootstrap source**: tooling repository `project-template/.pyproject.meta.toml` when creating a new project

#### `pyproject.toml` (in each project)
- **Purpose**: Generated file combining metadata + configs
- **Contents**: Full `[build-system]`, `[project]`, and `[tool.*]` sections
- **Synced**: **No** — generated dynamically
- **Updated by**: `scripts/merge_pyproject.py` (called by sync script)
- **Location**: Git-ignored or committed (not synced)

### Workflow

1. **Update shared tooling config?**
   - Edit `pyproject.toml` in the tooling repository
   - Run `make sync-tooling` in consumer projects
   - Sync script merges and regenerates each project's `pyproject.toml`

2. **Update project metadata?**
   - Edit `.pyproject.meta.toml` (name, version, description)
   - Commit to git
   - Run `make sync-tooling` or `python3 scripts/merge_pyproject.py .` to regenerate

3. **Create new project from template?**
   - Copy `project-template/.pyproject.meta.toml` from the tooling repository into the new project
   - Update name, version, description in `.pyproject.meta.toml`
   - Run sync script -> generates project-specific `pyproject.toml`

### Sync Governance

- **Tooling-first:** If a file is normally synced into consumer repos, change it in `tooling` first.
  This includes shared scripts, shared docs, `.pre-commit-config.yaml`, and
  `tooling/pyproject.toml`.
- **Project-local:** Do not make consumer-only edits to `.pyproject.meta.toml`, `tooling.toml`,
  or generated `pyproject.toml` and expect them to flow back into `tooling`.
- **Python source of truth:** `tooling.toml [python].version` is the contract; `pyproject.toml`
  should receive `requires-python` through `scripts/merge_pyproject.py`, not manual edits.
- **Sync changes intentionally:** After a shared change lands in `tooling`, update consumer repos
  with `make sync-tooling`, regenerate derived files, then run verification before opening PRs.
- **Manual-update exception:** `scripts/sync_tooling.sh` is tooling-owned, but consumer repos may
  need it copied manually because it is excluded from normal sync.

### Benefits

- ✅ **DRY**: Tool configs defined once in tooling, used everywhere
- ✅ **Consistency**: All projects use same build backend and tool versions
- ✅ **Flexibility**: Projects can override tool settings in `.pyproject.meta.toml`
- ✅ **Simple metadata**: Only 5-6 lines per project vs 50+ with duplication
- ✅ **Easy updates**: Change tool config once, all projects update via next sync

## Implementation Details

- `scripts/merge_pyproject.py` - Reads `.pyproject.meta.toml` + `tooling/pyproject.toml`, merges, writes final file
- `sync_tooling.sh` - Calls merge script after syncing files
- `.pyproject.meta.toml` - In sync EXCLUDE_LIST so projects keep their own metadata
- `pyproject.toml` - Not synced from tooling; generated locally by the merge script

## See Also
- `scripts/merge_pyproject.py` - Implementation of merge logic
- `project-template/.pyproject.meta.toml` - Template for new projects
- `tooling.toml` - Per-project tooling sync configuration
- `README.md` - Repository overview and usage
