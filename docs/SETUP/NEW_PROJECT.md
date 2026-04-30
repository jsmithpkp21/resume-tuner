# Creating a New Project

This guide walks you through creating and bootstrapping a new project from the `project-template/` in the tooling repo.

## Prerequisites

Before starting, ensure you have:

- **Git** installed and configured (`git config --global user.name` and `git config --global user.email`)
- **GitHub CLI** (`gh`) installed and authenticated (`gh auth login`)
- **Docker** installed (or local Python 3.11.x if skipping Docker — runtime scripts compare major.minor only today; the strict-patch policy is tracked in [#167](https://github.com/jsmithpkp21/tooling/issues/167))
- **WSL 2** (on Windows) or native macOS/Linux shell
- **A GitHub repo created** for your new project (empty, no README)

For detailed setup, see:
- [GitHub CLI Authentication](./GITHUB_CLI_AUTH.md)
- [Docker + WSL Quick Start](./DOCKER_WSL_SETUP.md)

## Step 1: Copy the Project Template

Clone or download the `project-template/` directory from the tooling repo:

```bash
# Option A: Clone entire tooling repo and copy the template
git clone https://github.com/jsmithpkp21/tooling.git
cp -r tooling/project-template ~/projects/my-new-project
cd ~/projects/my-new-project

# Option B: Direct download (faster, if you just want the template)
curl -sSL https://github.com/jsmithpkp21/tooling/archive/refs/heads/main.tar.gz \
  | tar xz -f - tooling-main/project-template
mv tooling-main/project-template ~/projects/my-new-project
rm -rf tooling-main
cd ~/projects/my-new-project
```

Replace `my-new-project` with your actual project name.

## Step 2: Run Project Setup

The `scripts/setup.sh` script bootstraps your project by:
- Fetching the tooling repo at the specified version
- Running `sync_tooling.sh` to pull shared workflows, configs, and scripts
- Generating `pyproject.toml` from template metadata
- Creating `.tooling-sync-manifest.lock` to track synced state

### Basic Setup (No Optional Layers)

```bash
bash scripts/setup.sh
```

### Setup with Layers

Optional layers add language-specific tooling and examples:

```bash
# Playwright (browser testing framework)
bash scripts/setup.sh playwright

# API layer (FastAPI example)
bash scripts/setup.sh api

# Web layer (frontend, optional)
bash scripts/setup.sh web
```

Supported layers: `playwright`, `api`, `web`

**Environment variables** (optional, for advanced setups):

```bash
# Use a specific tooling version or branch
TOOLING_VERSION=v1.2.0 bash scripts/setup.sh

# Use a private/forked tooling repo
TOOLING_REPO=https://github.com/your-org/tooling bash scripts/setup.sh

# GitHub token (for private repos).
# Prefer pulling the token from GitHub CLI instead of typing it directly:
export GITHUB_TOKEN="$(gh auth token)"
bash scripts/setup.sh
# or, if running in CI, set GITHUB_TOKEN from your CI secret store before invoking setup.sh.
```

## Step 3: Configure Your Project Metadata

Edit `.pyproject.meta.toml` to customize package name, description, and author:

```toml
[project]
name = "my-new-project"  # Change this
description = "My project description"  # Change this
version = "0.0.1"
authors = [
  { name = "Your Name", email = "you@example.com" },  # Change this
]
```

After editing, regenerate `pyproject.toml`:

```bash
# Recommended: make sync-tooling calls merge_pyproject.py with a known tooling source
make sync-tooling

# Or directly, with an explicit tooling path:
TOOLING_DIR=/path/to/tooling python3 scripts/merge_pyproject.py .
# e.g. if you cloned tooling alongside this project:
TOOLING_DIR=../tooling python3 scripts/merge_pyproject.py .
```

This merges your metadata with the shared config from `tooling.toml`.

## Step 4: Connect to GitHub Remote

`scripts/setup.sh` from Step 2 already ran `git init` if you weren't already inside a git repo, so you only need to commit the bootstrap state and push:

```bash
git add .
git commit -m "chore(bootstrap): initialize from project-template"
git branch -M main
git remote add origin https://github.com/your-org/my-new-project.git
git push -u origin main
```

## Step 5: Bootstrap the Local Environment

Run the full setup sequence:

```bash
make setup
```

This:
- Creates a Python virtual environment at `~/envs/<repo>-env`
- Installs dependencies from `requirements.txt`
- Installs pre-commit hooks for commit linting and drift checks
- Verifies the runtime environment (Python, gawk, shell tools)

## Step 6: Verify Everything Works

```bash
# Run linters and formatters
make lint

# Run tests
make test

# Run main quality gate (lint, type checks, tests, config/version/workflow checks)
make check

# Run sync drift and markdown checks separately
make drift-check
make markdown-lint
```

All should pass. If they don't, check [Troubleshooting](#troubleshooting) below.

## Understanding Key Files

### `.tooling-sync-manifest.toml`

Declares which files are synced from tooling into your project. This is the **allow-list**:
- Only files listed here are synced
- Synced files are managed by tooling; local edits are flagged by drift checks and can be overwritten on the next `make sync-tooling` run
- To update synced files, run `make sync-tooling`

### `.tooling-sync-manifest.lock`

Records the **applied state** of synced files:
- Generated after first `setup.sh` run
- Tracks hashes and versions of synced files
- Pre-commit hook checks for drift (changes to managed files)
- Commit this file; it's your sync state record

### `.pyproject.meta.toml`

**Your** project metadata (name, description, author):
- Edit this when you want to change package info
- Run `scripts/merge_pyproject.py` to regenerate `pyproject.toml`
- Do **not** edit `pyproject.toml` directly (it's generated)

### `tooling.toml`

**Your** project-specific tool config. Keys actually parsed by tooling scripts today:
- `[python].version` — source of truth for `requires-python` and env scripts (`scripts/create_env.sh`, `scripts/verify_env.sh`, `scripts/merge_pyproject.py`)
- `[tooling].pip` — pip version pin (read by `create_env.sh` / `verify_env.sh`)
- Top-level `repo = "..."` — tooling source URL (read by `scripts/sync_tooling.sh`)
- Top-level `version = "main"` — change to pin a specific tooling release

Documented but not yet enforced from this file:
- `[runtime].awk_impl` and `[runtime].shell_tools` — the contract is documented here, but `scripts/create_env.sh` and `scripts/verify_env.sh` currently hardcode the required-tools list (`bash awk grep sed`) and the gawk check rather than reading these keys.

Note: lint/type-tool config (ruff, mypy, etc.) lives in the generated
`pyproject.toml` `[tool.*]` tables, not in `tooling.toml`. Older copies of
this template carried unused `[black]`, `[isort]`, `[mypy]`, and `[flake8]`
sections; those have been removed because `scripts/merge_pyproject.py` does
not read them. If your consumer's `tooling.toml` still has them after a sync,
delete them.

## Syncing Tooling Updates

When new fixes or features land in the `tooling` repo, sync them into your project:

```bash
# Using make (recommended)
make sync-tooling

# Or directly
bash scripts/sync_tooling.sh
```

This:
- Fetches the tooling version specified in `tooling.toml`
- Syncs all files listed in `.tooling-sync-manifest.toml`
- Updates `.tooling-sync-manifest.lock`
- Removes files no longer in the manifest (by default)

**To review changes before committing:**

```bash
git status
git diff
```

**To keep removed files (don't delete):**

```bash
SYNC_NO_DELETE=1 bash scripts/sync_tooling.sh
```

## Using Docker for Local Development

For consistency and to avoid local Python/tool mismatches:

```bash
# Start the development container
docker compose up -d

# Run commands inside the container
docker compose exec base_env bash
# Now you're inside the container; run make targets normally
make setup
make lint
make test
```

See [Docker + WSL Quick Start](./DOCKER_WSL_SETUP.md) for details.

## Available Layers

Layers are optional add-ons that scaffold language/framework-specific structure:

### `playwright` — Browser Testing

```bash
bash scripts/setup.sh playwright
```

Adds:
- `layers/playwright/` with example Playwright tests
- `tests/e2e/` directory
- Playwright dependencies in `requirements.txt`

Use when: Building web apps with browser automation tests.

### `api` — FastAPI Example

```bash
bash scripts/setup.sh api
```

Adds:
- `src/api/` with example FastAPI app structure
- Example routes and models
- API test examples

Use when: Building HTTP APIs.

### `web` — Frontend (Future)

Currently a placeholder; adds frontend scaffolding in future versions.

## Troubleshooting

### Error: Python version mismatch

**Symptom:**
```
ERROR: Required interpreter python3.11 not found.
# or
ERROR: Python version mismatch
Expected: 3.11 (from 3.11.14)
Found:    <different-major.minor>
```

**Fix:** Install Python 3.11 and confirm it is available in your shell:

```bash
python3.11 --version
command -v python3.11

# Ubuntu/Debian
sudo apt install python3.11 python3.11-venv python3.11-dev

# Then re-run make setup
```

Or use Docker (which has the right Python pre-installed):

```bash
docker compose exec base_env bash
make setup
```

### Error: gawk not found

**Symptom:**
```
ERROR: awk implementation must be GNU Awk (gawk)
```

**Fix:** Install gawk:

```bash
# macOS
brew install gawk

# Ubuntu/Debian
sudo apt-get install gawk

# Or use Docker (gawk is pre-installed)
```

### Error: Drift check fails

**Symptom:**
```
ERROR: Drift detected in managed files. Run make sync-tooling to update.
```

**Cause:** You edited a synced file (or it changed externally).

**Fix:** Either:
1. Restore the file to tracked state: `git checkout <file>`
2. Or re-sync: `make sync-tooling` (will overwrite your changes)

**To bypass temporarily** (not recommended):

```bash
# The drift check runs at the push stage; bypass with pre-commit's SKIP mechanism:
SKIP=tooling-drift-check git push
```

### Error: Workflow action pins out of date

**Symptom:**
```
ERROR: Workflow action pins not in lock file
```

**Cause:** Workflows were manually edited or synced without updating the pin lock.

**Fix:** Regenerate the lock:

```bash
make action-pin-fix
make action-pin-check
git add .github/workflow-action-lock.json
git commit -m "chore: regenerate action pin lock"
```

### make setup hangs or takes forever

**Symptom:** `make setup` stuck downloading dependencies.

**Causes & fixes:**

1. Network issue: Check your internet connection
2. pip slow: Try `pip install --upgrade pip` inside the venv
3. Stale virtualenv: Force recreation:
   ```bash
   rm -rf ~/envs/<repo>-env
   make setup
   ```
4. Use Docker instead (faster, no local Python conflicts):
   ```bash
   docker compose up -d
   docker compose exec base_env make setup
   ```

## Next Steps

Once bootstrap is complete:

1. **Read the architecture docs:**
   - [Sync Manifest Reference](../REFERENCE/SYNC_MANIFEST.md)
   - [pyproject.toml Architecture](../REFERENCE/PYPROJECT_ARCHITECTURE.md)

2. **Start development:**
   - Add source code to `src/`
   - Write tests in `tests/`
   - Run `make lint` and `make test` frequently

3. **Set up CI/CD:**
   - Workflows are auto-synced; they run on push/PR
   - Configure branch protection in GitHub Settings

4. **Keep tooling updated:**
   - Check `tooling` repo releases periodically
   - Update `tooling.toml` version pin when ready
   - Run `make sync-tooling` to apply updates

## Getting Help

- **Tooling issues:** Open an issue in [jsmithpkp21/tooling](https://github.com/jsmithpkp21/tooling)
- **Project-specific issues:** Create an issue in your project repo
- **Pre-commit/hooks problems:** See [GIT_STAGING_GUIDE.md](./GIT_STAGING_GUIDE.md)
- **Docker problems:** See [DOCKER_WSL_SETUP.md](./DOCKER_WSL_SETUP.md)
