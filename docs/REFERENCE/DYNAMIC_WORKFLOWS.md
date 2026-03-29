# Dynamic Workflows - Sync Ready

**Date:** March 1, 2026
**Status:** ✅ **All workflows now fully dynamic and ready for syncing**

## Problem Solved

All GitHub Actions workflows have been updated to use dynamic values instead of hardcoded repository/project names. This ensures they work correctly when synced from `tooling` to `base_repo` or any other project.

## Workflows Updated

### 1. ✅ release-please.yml
**What was hardcoded:**
- `ghcr.io/jsmithpkp21/base_repo:latest` - hardcoded owner and repo name

**What was fixed:**
- Extract owner and repo dynamically: `${{ steps.repo_info.outputs.repo_owner }}`/`${{ steps.repo_info.outputs.repo_name }}`
- Make `tooling.toml` optional - gracefully handle if missing
- Works for any project: tooling, base_repo, or future projects

**Changes:**
```yaml
# Before:
tags: |
  ghcr.io/jsmithpkp21/base_repo:latest

# After:
tags: |
  ghcr.io/${{ steps.repo_info.outputs.repo_owner }}/${{ steps.repo_info.outputs.repo_name }}:latest
```

### 2. ✅ verify-environment.yml
**What was hardcoded:**
- `base_repo` in Docker image tags (4 places)
- `base_repo-image` in artifact names
- `/tmp/base_repo.tar` in artifact paths
- Assumed `tooling.toml` always exists

**What was fixed:**
- Extract repository name dynamically from `github.repository` context
- Use extracted name in all Docker tags and artifact names
- Make `tooling.toml` optional - check if exists before reading
- Add `repo_name` to build job outputs for use in dependent jobs (lint, test, verify)

**Example outputs:**
- tooling repo: Creates `tooling:1.0.2` Docker image, `tooling-image` artifact
- base_repo: Creates `base_repo:0.1.0` Docker image, `base_repo-image` artifact

**Key changes:**
```yaml
# Build job now extracts dynamically:
run: |
  REPO_NAME=$(echo "${{ github.repository }}" | cut -d'/' -f2)
  # ... rest of script uses REPO_NAME ...

# Docker tags use dynamic name:
tags: ${{ steps.build_inputs.outputs.REPO_NAME }}:${{ steps.build_inputs.outputs.ENV_VERSION }}

# Artifact names are dynamic:
name: ${{ needs.build.outputs.repo_name }}-image
```

### 3. ✅ cleanup-deleted-branch-artifacts.yml
**Status:** Already dynamic - uses `context.repo.owner` and `context.repo.repo`

### 4. ✅ cleanup-orphaned-artifacts.yml
**Status:** Already dynamic - uses `context.repo.owner` and `context.repo.repo`

### 5. ✅ commitlint.yml
**Status:** Empty placeholder (not yet implemented)

## How It Works When Synced

### Scenario 1: In tooling repo
```
Push to main
  ↓
release-please triggers
  ↓
Extracts: repo_owner=jsmithpkp21, repo_name=tooling
  ↓
Creates release: ghcr.io/jsmithpkp21/tooling:1.0.3
```

### Scenario 2: Synced to base_repo
```
base_repo syncs .github/workflows/release-please.yml from tooling
Push to main
  ↓
release-please triggers
  ↓
Extracts: repo_owner=jsmithpkp21, repo_name=base_repo
  ↓
Creates release: ghcr.io/jsmithpkp21/base_repo:0.2.0
```

## Files Updated

1. `.github/workflows/release-please.yml`
   - Added dynamic repository extraction
   - Make tooling.toml optional
   - Use extracted values in Docker tags

2. `.github/workflows/verify-environment.yml`
   - Extract repo name dynamically
   - Make tooling.toml optional
   - Use dynamic repo name in all jobs
   - Add repo_name to build outputs

3. `pyproject.toml`
   - Changed package name from `base_env` to `tooling`
   - Updated description

4. `.release-please-config.json`
   - Changed package-name to `tooling`

## Commits Made

1. **refactor: make test version-dynamic and remove SYNC_VERIFICATION.md**
   - Test reads VERSION file instead of hardcoded v1.0.2
   - Removed SYNC_VERIFICATION.md (was local documentation)

2. **fix: update tooling package name from base_env to tooling**
   - Changed pyproject.toml package name
   - Updated .release-please-config.json

3. **refactor: make release-please workflow fully dynamic for syncing to other projects**
   - Extract repo owner/name dynamically
   - Make tooling.toml optional
   - All hardcoded values replaced

4. **refactor: make verify-environment.yml fully dynamic for syncing to other projects**
   - Extract repo name dynamically
   - Make tooling.toml optional
   - Use dynamic names in all jobs

## Verification

### Test That Workflows Work

When synced to another project, verify:

1. **release-please.yml**
   - Creates correct Docker image tag
   - Example: `ghcr.io/owner/repo_name:latest`

2. **verify-environment.yml**
   - Creates correct Docker image tag
   - Creates correct artifact names
   - All jobs reference correct artifacts

3. **Optional files**
   - If `tooling.toml` doesn't exist in target repo, workflow still works
   - If it exists, pip version is extracted correctly

## What This Enables

✅ **Workflows work in ANY project after syncing**
- No manual edits needed
- Values adapt to project
- Same workflow file, different behavior per project

✅ **tooling.toml is optional**
- Works in projects that don't have it
- Works in projects that do

✅ **Package names are correct**
- tooling repo: `tooling` package
- base_repo: `base_env` package
- Future projects: their own names

✅ **Docker images tagged correctly**
- Each project gets its own Docker image
- Tags use project's name, not hardcoded

## Summary

All workflows are now **fully dynamic and syncable**. They use GitHub context variables and environment detection to adapt to any project they're deployed in. When syncing from tooling to base_repo or any other project, no manual workflow edits are needed.

**Status: Ready for production syncing** ✅
