# Fix: GitHub Actions Cannot Create Pull Requests

## Problem
```
release-please failed: GitHub Actions is not permitted to create or approve pull requests.
```

This error occurs when branch protection rules on `main` prevent GitHub Actions from creating pull requests, even though the workflow has `pull-requests: write` permission.

## Root Cause
GitHub's branch protection rules are MORE restrictive than workflow permissions. Even with the correct permissions in the workflow, the branch protection settings must explicitly allow GitHub Actions (or deployments/builds) to create/approve PRs.

## Solution - Enable GitHub Actions to Create Pull Requests

### Step 1: Navigate to Repository Settings
1. Go to your GitHub repository (e.g., [https://github.com/jsmithpkp21/tooling](https://github.com/jsmithpkp21/tooling))
2. Click **Settings** (under your repository name in top navigation)
3. In the left sidebar, click **Actions**
4. Click **General**

### Step 2: Enable Pull Request Creation
1. Scroll down to the **"Workflow permissions"** section
2. Find the checkbox: **"Allow GitHub Actions to create and approve pull requests"**
3. ✅ **Check this box**

### Step 3: Save Changes
1. Click the **Save** button at the bottom of the page
2. The setting will be applied immediately

**That's it!** This is the ONLY setting you need to change.

## Verification Steps

After enabling the setting:

1. **Push a commit** to `main`:
   ```bash
   cd ~/projects/tooling
   git add -A
   git commit -m "test: trigger release-please"
   git push origin main
   ```

2. **Check GitHub Actions**:
   - Go to **Actions** tab in your GitHub repo
   - Look for "release-please" workflow
   - Verify it runs successfully (no more permission errors)

3. **Check for Release PR**:
   - Go to **Pull Requests** tab
   - You should see a PR created by `github-actions[bot]`
   - Title should be like "chore: release 1.0.3" or similar

## Visual Guide

The setting location:
```
Repository → Settings → Actions → General
    ↓
Scroll down to "Workflow permissions"
    ↓
☑ Allow GitHub Actions to create and approve pull requests
    ↓
Click "Save"
```

## If Still Not Working

### Option A: Check Organization Settings (If in an Organization)
If this repository is part of a GitHub organization:
1. Go to **Organization Settings** (not repository settings)
2. Click **Actions** → **General**
3. Under "Policies", ensure "Allow all actions and reusable workflows" is selected
4. Under "Workflow permissions", ensure the same checkbox is enabled at the organization level

### Option B: Use Personal Access Token (Advanced)
If the above doesn't work, you can use a Personal Access Token instead of `GITHUB_TOKEN`:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it these scopes:
   - `repo` (full control of private repositories)
   - `workflow` (update GitHub Action workflows)
4. Copy the token
5. Add it to your repository secrets:
   - Go to Repository Settings → Secrets and variables → Actions
   - Click "New repository secret"
   - Name: `RELEASE_PLEASE_TOKEN`
   - Value: paste your token
6. Update `.github/workflows/release-please.yml`:
   ```yaml
   - uses: googleapis/release-please-action@v4.1.4
     with:
       token: ${{ secrets.RELEASE_PLEASE_TOKEN }}
   ```


## Commit Changes

Once you fix the GitHub settings, the workflow should work automatically. No code changes needed.

**Status:**
- ✅ Workflow code is correct
- ⏳ **Waiting on: GitHub repository configuration**

## Next Steps

1. ✅ Go to Repository Settings → Actions → General
2. ✅ Enable "Allow GitHub Actions to create and approve pull requests"
3. ✅ Save the setting
4. Push any commit to trigger the workflow and verify it creates the release PR
5. Merge the release PR
6. Verify tag and GitHub release are created automatically

## References

- [GitHub Docs: Branch Protection Rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches)
- [GitHub Docs: Requiring status checks before merging](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/requiring-status-checks-before-merging)
- [Release-Please Documentation](https://github.com/googleapis/release-please)

## Key Point

**This is NOT a code issue.** The workflow code is correct and has proper permissions. You need to enable one GitHub repository setting:

**Repository Settings → Actions → General → "Allow GitHub Actions to create and approve pull requests"**

That's the only configuration change needed. Branch protection rules (rulesets) do NOT need to be modified.
