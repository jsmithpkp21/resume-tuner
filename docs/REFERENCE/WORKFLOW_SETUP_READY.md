# Workflow Automation Setup - Usage Guide

## Overview

This repository includes workflow automation features already implemented:
- ✅ Conventional commit enforcement (via conventional-pre-commit hook)
- ✅ Automatic semantic versioning (Release Please workflow)
- ✅ Auto-generated release notes and CHANGELOG

Additional workflow features are being planned and tracked via GitHub issues:
- Branch naming conventions
- PyCharm IDE integration
- Automatic cleanup of merged branches
- Issue/PR templates

## Quick Start

### Available Features

#### 1. ✅ Conventional Commits Enforcement
Implemented via `.pre-commit-config.yaml` using `conventional-pre-commit` hook.
All commits are automatically validated on `commit-msg` stage.

See `CONTRIBUTING.md` for commit format guidelines.

#### 2. ✅ Automatic Semantic Versioning (Release Please)
Implemented via `.github/workflows/release-please.yml`.

**How it works:**
- Push commits to `main` with conventional format
- Release Please analyzes commits and creates release PR
- Automatically updates VERSION, CHANGELOG, and creates GitHub releases

**Commit types trigger version bumps:**
- `feat:` → Minor version bump (0.1.0 → 0.2.0)
- `fix:` → Patch version bump (0.1.0 → 0.1.1)
- `BREAKING CHANGE:` → Major version bump (0.1.0 → 1.0.0)
- `docs:`, `chore:`, `test:`, etc. → No version bump

### Creating Workflow Tracking Issues (Optional)

If you want to create GitHub issues for remaining workflow features:

```bash
# Create custom labels
python3 scripts/setup_github_labels.py

# Create tracking issues
python3 scripts/create_workflow_automation_issues.py
```

This creates 4 GitHub issues for remaining features:
1. Create branch creation helper script
2. Configure PyCharm plugin for commit validation
3. Enable auto-delete merged branches
4. Add issue/PR templates

## What's Available

### Implemented Workflows

- **`.github/workflows/release-please.yml`** - Automatic semantic versioning and releases
- **`.pre-commit-config.yaml`** - Conventional commits enforcement

### Helper Scripts

- **`scripts/setup_github_labels.py`** - Create custom GitHub labels (optional)
- **`scripts/create_workflow_automation_issues.py`** - Create tracking issues (optional)

### Documentation

- **`docs/WORKFLOW_AUTOMATION_PLAN.md`** - Complete implementation plan and architecture
- **`CONTRIBUTING.md`** - Contributor guide with commit conventions
- **`docs/SETUP/GITHUB_CLI_AUTH.md`** - GitHub CLI authentication guide

## Implementation Timeline

**Completed:**
- ✅ Conventional Commits enforcement - Complete
- ✅ Release Please versioning - Complete

**Remaining (if implementing):**
Total estimated effort: ~55 minutes for remaining 4 features

| Task | Effort | Status |
|------|--------|--------|
| Branch helper script | 15 min | Planned |
| PyCharm plugin setup | 10 min | Planned |
| Auto-delete branches | 5 min | Planned |
| Issue/PR templates | 25 min | Planned |

## Next Steps

1. ✅ Commits automatically validated using conventional-pre-commit hook
2. ✅ Releases automatically created when merging to main
3. (Optional) Create tracking issues for remaining features using helper scripts
4. (Optional) Implement remaining workflow features in priority order

For detailed architecture and rationale, see `docs/WORKFLOW_AUTOMATION_PLAN.md`.
