# GitHub Branch Protection Setup Instructions

## Step-by-Step Configuration

### 1. Create New Branch Protection Rule

On the "Branch protection rules" page:
- Click **Add rule** button

### 2. Select Branch Targeting Criteria

GitHub presents these options. Choose ONE:

- [ ] **Include default branch** - Protects main/master (if it's your default)
- [ ] **Include all branches** - Protects every branch (too restrictive)
- [x] **Include by pattern** - Protects branches matching a pattern ✅ **CHOOSE THIS**
- [ ] **Exclude by pattern** - Exclude specific branches (not needed)

**For your setup: Select "Include by pattern"**

Then enter the pattern: `main`

This will protect only the `main` branch.

- Click **Create** to proceed

### 3. Configure Required Settings

Once you're in the rule configuration, enable these options:

#### ✅ Require a pull request before merging
- [x] Require pull request reviews before merging
  - Required number of reviewers: **1**
  - [x] Dismiss stale pull request approvals when new commits are pushed
  - [x] Require review from code owner (if .github/CODEOWNERS exists)
  - [x] Require approval of the most recent reviewable push
  - [x] Allow specified actors to bypass required pull requests (optional, for emergencies only)

#### ✅ Require status checks to pass before merging
- [x] Require branches to be up to date before merging
- [x] Require status checks to pass before merging

  **Select these status checks as REQUIRED:**
  - [ ] Lint Code
  - [ ] Run Tests
  - [ ] Verify Environment

#### ✅ Require conversation resolution before merging
- [x] Require all conversations on code to be resolved before merging

#### ✅ Restrict who can push to matching branches
- [x] Restrict who can push to matching branches
  - Choose: **Restrict to administrators**

#### ✅ Allow auto-merge (optional but recommended)
- [x] Allow auto-merge (optional)
  - Recommended: Squash and merge, or Create a merge commit

### 3. Save the Rule

Click **Save changes** at the bottom of the page.

---

## What This Enforces

Once configured, the `main` branch will:

✅ **Block direct commits** - Git hooks prevent local commits
✅ **Block direct pushes** - Git hooks prevent local pushes
✅ **Require pull request** - All changes must go through GitHub PR
✅ **Require 1+ approval** - Someone must review and approve
✅ **Require all 3 checks to pass:**
   - Lint Code (ruff linting)
   - Run Tests (pytest)
   - Verify Environment (environment validation)
✅ **Require conversation resolution** - All review comments must be resolved

---

## Branch Protection Flow

```
Feature Branch Created
    ↓
Changes Pushed
    ↓
Pull Request Created
    ↓
Status Checks Run (lint, test, verify)
    ├─ If any fail → PR blocked
    └─ If all pass → Continue
    ↓
Code Review Requested
    ├─ If rejected → PR blocked
    └─ If approved → Continue
    ↓
Resolve Conversations (if any)
    ├─ If unresolved → PR blocked
    └─ If resolved → Continue
    ↓
Merge to Main (via GitHub UI)
    ↓
Build Status Reflects Merge
```

---

## Testing Branch Protection

Once configured, test it:

1. **Try to commit to main locally:**
   ```bash
   git checkout main
   echo "test" > test.txt
   git add test.txt
   git commit -m "test"
   ```
   ✅ Should be blocked by pre-commit hook

2. **Try to push to main:**
   ```bash
   git checkout main
   git push origin main
   ```
   ✅ Should be blocked by pre-push hook

3. **Create a PR and verify GitHub checks:**
   - Create feature branch
   - Make a commit
   - Push and create PR
   - Verify all 3 status checks appear
   - Verify you can't merge until: all checks pass + 1 approval

---

## Configuration Complete ✅

Once you've saved the rule, branch protection is active on `main`:
- Local git hooks prevent mistakes
- GitHub enforces code review + all checks
- Zero way to bypass without admin override (emergency only)
