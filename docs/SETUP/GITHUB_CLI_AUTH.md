# GitHub CLI Authentication Quick Start

## Troubleshooting: `gh` Returns `HTTP 401: Bad credentials`

**Check this first before anything else:** your PAT has likely expired.

Fine-grained PATs default to 30-day expiry. GitHub sends an email warning before
expiry, but if missed the token silently stops working and `gh` returns `401` with
no clear "token expired" message.

```bash
# Quick diagnosis
gh auth status

# Fix: clear stale env overrides then re-login with a new PAT
unset GH_TOKEN
unset GITHUB_TOKEN
gh auth logout -h github.com || true
read -s -p "Paste new GitHub PAT: " GH_PAT
echo
printf '%s' "$GH_PAT" | gh auth login -h github.com --with-token
unset GH_PAT
gh auth setup-git
gh auth status
gh api user | cat
```

**Recommended PAT permissions (fine-grained, common tooling workflows):**

| Permission | Level |
|---|---|
| Contents | Read & Write |
| Issues | Read & Write |
| Pull requests | Read & Write |
| Actions | Read & Write |
| Workflows | Read & Write |
| Metadata | Read (auto) |

Set expiry to **90 days** and rotate before it expires to avoid the 401 cycle.

---

## Current Status

GitHub CLI (`gh`) is installed but needs authentication to create issues.

## Authentication Steps

Run this command:

```bash
gh auth login
```

**Prompts you'll see:**

1. **What account do you want to log into?**
   - Choose: `GitHub.com` (not Enterprise)

2. **What is your preferred protocol for Git operations?**
   - Choose: `HTTPS` or `SSH` (use SSH if you already have SSH keys set up)

3. **Authenticate GitHub CLI by logging in?**
   - Choose: `Login with a web browser` (easiest)

4. **You'll get a one-time code:**
   - Copy the code shown
   - Press Enter to open browser
   - Paste code in browser
   - Authorize GitHub CLI

5. **Done!** ✅

## Verify Authentication

```bash
gh auth status
```

Should show:
```
✓ Logged in to github.com as jsmithpkp21 (oauth_token)
✓ Git operations protocol: ssh
✓ Token: gho_************************************
```

## Once Authenticated

Run the script to create issues:

```bash
python3 scripts/create_workflow_automation_issues.py
```

This will create 6 issues in your repository.

## Alternative: Manual Issue Creation

If you prefer not to authenticate, you can create issues manually in GitHub UI:
1. Go to: [https://github.com/jsmithpkp21/base_repo/issues](https://github.com/jsmithpkp21/base_repo/issues)
2. Click "New issue"
3. Create each of the 6 issues from WORKFLOW_AUTOMATION_PLAN.md

But the script is faster! 🚀
