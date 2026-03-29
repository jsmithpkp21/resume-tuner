# GitHub Issues Automation Guide
This document explains how to set up automated GitHub issue creation and branch management for your project.
---
## OPTION 1: Use the Python Script (Recommended)
### Step 1: Install GitHub CLI
On WSL/Ubuntu:
```bash
sudo apt-get install gh
```
### Step 2: Authenticate with GitHub
```bash
gh auth login
# Follow prompts to authenticate
```
### Step 3: Run the issue creation script
```bash
cd /path/to/base_repo
python3 scripts/create_github_issues.py
```
This will:
- Create all outstanding issues
- Print issue numbers
- Suggest branch names for each
---
## OPTION 2: Manual GitHub Web UI
Go to: [https://github.com/jsmithpkp21/base_repo/issues/new](https://github.com/jsmithpkp21/base_repo/issues/new)
For each task, create an issue with:
- **Title:** Clear, descriptive
- **Labels:** enhancement, bug, documentation, etc.
- **Body:** Include description, tasks, acceptance criteria
---
## Branching Workflow
Once issue is created, follow this workflow:
### 1. Create a feature branch for the issue
```bash
git checkout -b #<ISSUE_NUM>-short-description
```
Example:
```bash
git checkout -b #15-add-make-build-playwright
```
### 2. Link branch to issue
Commit messages should reference the issue:
```bash
git commit -m "feat: Add make build-playwright target
Closes #15"
```
### 3. Work on the feature
- Follow coding standards from `.github/copilot-instructions.md`
- Run: `make lint`, `make test` to verify
- Commit regularly
### 4. Push and create Pull Request
```bash
git push origin #15-add-make-build-playwright
```
Then on GitHub:
- Click "Compare & Pull Request"
- Link to issue in PR description: `Closes #15`
- Request code review
- Require all checks to pass before merge
### 5. After merge
```bash
git checkout main
git pull origin main
git branch -d #15-add-make-build-playwright
```
---
## Branch Naming Convention
**Format:** `#<ISSUE_NUM>-<SHORT-DESCRIPTION>`
**Examples:**
- `#1-add-make-build-playwright`
- `#2-create-layer-readme`
- `#3-debug-terminal-issue`
- `#15-add-fastapi-layer`
**Benefits:**
- Automatically links branch to GitHub issue
- Easy to track which branch addresses which issue
- Clear history in git log
---
## GitHub Branch Protection (Already Enabled)
Your repository has branch protection on `main`:
**Requirements:**
1. ✅ Code review required (1+ approval)
2. ✅ All status checks must pass:
   - lint (ruff, black, isort, mypy)
   - test (pytest)
   - verify (scripts/verify_env.sh)
**Process:**
1. Create feature branch from issue
2. Make changes locally
3. Push branch: `git push origin #<NUM>-description`
4. Create Pull Request on GitHub
5. All checks automatically run
6. Wait for code review approval
7. GitHub will allow merge only if all pass
---
## Quick Reference: Common Tasks
### Create all issues from TODO
```bash
python3 scripts/create_github_issues.py
```
### Create a feature branch
```bash
git checkout -b #15-feature-description
```
### Work on feature
```bash
make lint-fix     # Fix any issues
make test         # Run tests
git add .
git commit -m "feat: Description. Closes #15"
```
### Push to GitHub
```bash
git push origin #15-feature-description
```
### On GitHub
1. Go to Pull Requests
2. Click "Compare & pull request"
3. Add description: "Closes #15"
4. Request review
5. Wait for approval + all checks
6. Merge when ready
### After merge
```bash
git checkout main
git pull origin main
git branch -d #15-feature-description
```
---
## Issue Labels Used
| Label | Purpose |
|-------|---------|
| `enhancement` | New features, improvements |
| `bug` | Bug fixes, issues |
| `documentation` | Documentation updates |
| `refactor` | Code refactoring |
| `ci-cd` | CI/CD pipeline changes |
| `layers` | Layer-related tasks |
| `python` | Python code changes |
| `makefile` | Makefile changes |
| `scripts` | Script changes |
| `terminal` | Terminal/WSL issues |
| `wsl` | WSL-specific issues |
| `high-priority` | Blocking or urgent |
| `github-actions` | GitHub Actions workflows |
| `architecture` | Architecture/design changes |
---
## Tracking Progress
### See all open issues
[https://github.com/jsmithpkp21/base_repo/issues](https://github.com/jsmithpkp21/base_repo/issues)
### See issues by label
- [https://github.com/jsmithpkp21/base_repo/issues?labels=enhancement](https://github.com/jsmithpkp21/base_repo/issues?labels=enhancement)
- [https://github.com/jsmithpkp21/base_repo/issues?labels=bug](https://github.com/jsmithpkp21/base_repo/issues?labels=bug)
### See your open PRs
[https://github.com/jsmithpkp21/base_repo/pulls](https://github.com/jsmithpkp21/base_repo/pulls)
---
## Automation Tips
### 1. Link commits to issues
Mention issue in commit: `"Fixes #15"`
GitHub auto-closes issue when PR is merged.
### 2. Track multiple issues in one PR
```
Fixes #15, Fixes #16, Fixes #17
```
### 3. Reference issues from other places
In comments: "This is handled in #15"
GitHub creates links automatically.
### 4. Use issue templates
When creating issues, use templates for consistency.
Templates are in `.github/ISSUE_TEMPLATE/`
---
## Next Steps
1. ✅ Ensure GitHub CLI is installed: `which gh`
   - If not found: `sudo apt-get install gh`
2. ✅ Authenticate: `gh auth login`
3. ✅ Create all issues: `python3 scripts/create_github_issues.py`
4. ✅ View your new issues: [https://github.com/jsmithpkp21/base_repo/issues](https://github.com/jsmithpkp21/base_repo/issues)
5. ✅ Pick an issue and start work: `git checkout -b #<NUM>-description`
6. ✅ Follow the feature branch workflow above
