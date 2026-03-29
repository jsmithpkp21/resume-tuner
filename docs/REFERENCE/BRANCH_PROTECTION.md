# GitHub Branch Protection Rules Configuration

This file documents the required branch protection settings for this repository.

## ⚠️ IMPORTANT: These settings must be configured manually on GitHub

The branch protection rules are NOT automatically enforced. You must configure them on GitHub:

1. Go to: **Settings** → **Branches** → **Add rule**
2. Branch name pattern: `main`
3. Configure the settings below
4. Save the rule

Without these settings, contributors can bypass code review and merge directly to main.

---

# For main branch protection, use GitHub CLI:
# gh repo edit --enable-auto-merge --require-code-review-from 1 --dismiss-stale-reviews

## Required Settings (Configure in GitHub UI)

### For 'main' branch:
1. **Require a pull request before merging**
   - Required approvals: 1
   - Dismiss stale pull request approvals when new commits are pushed: ✓
   - Require approval of the most recent reviewable push: ✓

2. **Require status checks to pass before merging**
   - Require branches to be up to date before merging: ✓
   - Required status checks:
     - `Lint Code` (make lint)
     - `Run Tests` (make test)
     - `Verify Environment` (make verify)

3. **Require code review before merge**
   - Minimum 1 approval required
   - Require review from code owner: ✓ (if .github/CODEOWNERS exists)

4. **Require conversation resolution before merging**
   - Comments must be resolved: ✓

5. **Restrict who can push to matching branches**
   - Restrict who can force push: ✓

### For 'develop' branch (if exists):
1. Require pull request: ✓
2. Require 1 code review: ✓
3. Status checks: lint, test

## Local Git Hooks

Git hooks are automatically installed via the pre-commit framework when you run `make setup` or `make bootstrap` in this repository:

```bash
make setup
```

This runs the following command internally:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

This will install the pre-commit wrapper into `.git/hooks/` and enable all hooks configured in `.pre-commit-config.yaml`, including the local hooks that block:
- Direct commits to main
- Direct pushes to main on origin

### ⚠️ Do not edit .git/hooks/* directly

**Manually creating or modifying `.git/hooks/pre-commit` or `.git/hooks/pre-push` will overwrite the pre-commit wrapper and disable the configured hook suite** (linting, tests, type checks, secrets scanning, and branch protection hooks).

If you need to change the behavior of these hooks, update `.pre-commit-config.yaml` and re-run:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

### What hooks are enabled?

The pre-commit framework manages the following checks:
- **Branch protection:** Blocks commits/pushes to `main` branch
- **Code quality:** Runs ruff, black, isort, mypy on Python files
- **Security:** Checks for secrets, private keys, large files
- **Tests:** Validates tests can be collected with pytest
- **File validation:** YAML/TOML/JSON syntax checks

## Workflow for Contributors

### Creating a Feature Branch:
```bash
git checkout -b feature/your-feature-name
git add .
git commit -m "feat: Description of changes"
git push origin feature/your-feature-name
```

### Creating a Pull Request:
1. Go to GitHub.com
2. Click "New Pull Request"
3. Select your feature branch → main
4. Add description of changes
5. Request review from team members
6. Wait for:
   - ✓ All status checks (lint, test) to pass
   - ✓ At least 1 code review approval
   - ✓ All conversations resolved
7. Merge with "Squash and merge" or "Create a merge commit"

### After Merge:
```bash
git checkout main
git pull origin main
git branch -d feature/your-feature-name
```

## GitHub CLI Commands

### Set up branch protection (requires admin access):
```bash
# Protect main branch
gh repo edit \
  --enable-auto-merge \
  --require-code-review-from 1 \
  --dismiss-stale-reviews \
  --require-status-checks \
  --status-checks-require-latest

# Add required status checks
gh api repos/{owner}/{repo}/branches/main/protection \
  -f required_status_checks='{"strict":true,"contexts":["lint","test"]}'
```

## Exceptions

**Only authorized team members can:**
- Force push to main (use with caution)
- Bypass code review (emergency only)
- Merge without status checks (not recommended)

**Request through:**
- GitHub Issue
- Team Slack/Chat
- Pull request comment with justification

---

## Current Status

✅ Repository configured for code review requirement
✅ Pull request workflow enforced via GitHub
⏳ Local git hooks can be installed for extra safety

See CONTRIBUTING.md for contributor guidelines
