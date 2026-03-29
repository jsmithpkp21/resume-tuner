# GitHub Issues Setup - Quick Start Guide

## ✅ What We've Created For You

### 1. Automated Issue Creation Script
**File:** `scripts/create_github_issues.py`

This Python script will automatically create all outstanding tasks as GitHub issues. It includes:
- 10 ready-to-create issues from your TODO.md
- Automatic labeling (enhancement, bug, documentation, etc.)
- Issue descriptions with detailed acceptance criteria
- Suggested branch names for each issue

### 2. GitHub Issues Workflow Guide
**File:** `docs/GITHUB_ISSUES_GUIDE.md`

Comprehensive guide covering:
- Two ways to create issues (automated script or manual)
- Branch naming conventions
- Feature branch workflow
- Pull request process
- Branch protection rules
- Issue tracking and automation tips

### 3. Issue Template
**File:** `.github/ISSUE_TEMPLATE/feature.md`

Standardized template for creating feature request issues consistently.

---

## 🚀 How to Use

### Step 1: Install GitHub CLI (One-time setup)

```bash
# On WSL/Ubuntu
sudo apt-get update
sudo apt-get install gh

# Verify installation
gh --version
```

### Step 2: Authenticate with GitHub

```bash
gh auth login
# Follow prompts:
# - Select "GitHub.com"
# - Choose "HTTPS" for protocol
# - Choose "Paste an authentication token" or "Login with web browser"
# - Complete authentication
```

### Step 3: Create All Issues

```bash
cd ~/projects/base_repo
python3 scripts/create_github_issues.py
```

This will:
- Create 10 issues automatically
- Print issue numbers and suggested branch names
- Show a quick reference at the end

### Step 4: View Your Issues

Go to: [https://github.com/jsmithpkp21/base_repo/issues](https://github.com/jsmithpkp21/base_repo/issues)

---

## 📋 Issues That Will Be Created

| Issue | Title | Labels |
|-------|-------|--------|
| #1 | Add make build-playwright target to Makefile | enhancement, makefile |
| #2 | Create layers/playwright/README.md documentation | documentation, layers |
| #3 | Create Layer Architecture documentation | documentation, architecture |
| #4 | Create prepare_selenium_layer.py script | enhancement, layers, python |
| #5 | Create prepare_fastapi_layer.py script | enhancement, layers, python |
| #6 | Create generic layer_builder.py base class | refactor, layers, python |
| #7 | Create activate_layer.sh script | enhancement, scripts |
| #8 | Add GitHub Actions CI/CD layer testing | ci-cd, layers, github-actions |
| #9 | Create resolve_layer_deps.py script | feature, layers, python |
| #10 | Add Makefile layer management targets | enhancement, makefile |
| #11 | Create Layers Guide documentation | documentation, layers |
| #12 | Debug terminal stdout suppression issue | bug, terminal, wsl |

---

## 🔗 Feature Branch Workflow

Once issues are created, follow this workflow for each task:

### 1. Create feature branch from issue
```bash
git checkout -b #<ISSUE_NUM>-short-description

# Example:
git checkout -b #1-add-make-build-playwright
```

### 2. Make your changes
```bash
# Edit files as needed
# Test locally
make lint-fix
make test
```

### 3. Commit with issue reference
```bash
git add .
git commit -m "feat: Add make build-playwright target

Detailed description of changes...

Closes #1"
```

### 4. Push and create Pull Request
```bash
git push origin #1-add-make-build-playwright
```

Then on GitHub:
- Click "Compare & pull request"
- Ensure PR body says "Closes #1"
- Request code review
- Wait for all checks to pass
- Merge when approved

### 5. Clean up after merge
```bash
git checkout main
git pull origin main
git branch -d #1-add-make-build-playwright
```

---

## 🎯 Benefits of This Workflow

✅ **Organized tracking** - All tasks visible in GitHub Issues
✅ **Linked work** - Each branch and PR linked to an issue
✅ **Automatic closure** - Issues close when PRs merge
✅ **Code review** - Branch protection requires approval
✅ **CI/CD integration** - All checks run automatically
✅ **History** - Complete audit trail of what was done and why
✅ **Team collaboration** - Easy for others to see what's being worked on

---

## 📞 Troubleshooting

### "gh: command not found"
Install GitHub CLI:
```bash
sudo apt-get install gh
```

### "Error: authentication required"
Authenticate:
```bash
gh auth login
```

### "CalledProcessError" in script
The GitHub CLI failed. Common reasons:
- Not authenticated
- Internet connection issue
- GitHub API unavailable

Try again in a moment, or check status at [https://www.githubstatus.com/](https://www.githubstatus.com/)

---

## 📚 Next Steps

1. ✅ Install GitHub CLI: `sudo apt-get install gh`
2. ✅ Authenticate: `gh auth login`
3. ✅ Create issues: `python3 scripts/create_github_issues.py`
4. ✅ View issues: [https://github.com/jsmithpkp21/base_repo/issues](https://github.com/jsmithpkp21/base_repo/issues)
5. ✅ Pick an issue and start work using the feature branch workflow above
6. ✅ Create PRs for your work
7. ✅ Request code review and merge when approved

---

## 📖 Further Reading

- Full workflow guide: `docs/GITHUB_ISSUES_GUIDE.md`
- GitHub CLI docs: [https://cli.github.com/](https://cli.github.com/)
- GitHub Issues help: [https://docs.github.com/en/issues](https://docs.github.com/en/issues)
- GitHub Flow: [https://guides.github.com/introduction/flow/](https://guides.github.com/introduction/flow/)
