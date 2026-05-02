# Contributing & Development Guide

This guide is for maintainers and contributors working on the deterministic environment system itself.

---

## 🐳 Development Environment

Use Docker for a fully configured development environment:

```bash
# Start development container
docker-compose up -d

# All tools are pre-installed and ready to use
docker-compose exec base_env bash
```

See [DOCKER.md](DOCKER.md) for full Docker documentation.

---

## ⚠️ Branch Protection: Code Review Required

**ALL changes to `main` branch require:**
1. ✅ Pull request (no direct commits/pushes)
2. ✅ At least 1 code review approval
3. ✅ All status checks passing (lint, test, verify)
4. ✅ Conversation resolution

**Required Status Checks:**
- `Lint Code` - Ruff linting for code quality
- `Run Tests` - Pytest test suite
- `Verify Environment` - Environment validation

This is enforced by:
- **GitHub:** Branch protection rules (must be configured in Settings)
- **Local:** Git pre-commit and pre-push hooks

See [docs/REFERENCE/BRANCH_PROTECTION.md](docs/REFERENCE/BRANCH_PROTECTION.md) for setup instructions.

---

## Pull Request Workflow

### Child issue branches vs epic branches

For work that belongs to an active epic, use this flow:

- **Child issue branch → epic branch** during implementation
- **Epic branch → `main`** only when the epic is ready to land

For the current sync-hardening work, child issue PRs should target:
- `epic/58-sync-contract-hardening`

### Merge checklist (keep this visible while merging)

#### Child issue branch → epic branch
- [ ] Base branch is the active epic branch (for example `epic/58-sync-contract-hardening`)
- [ ] Head branch is the issue branch (`feature/...`, `fix/...`, `docs/...`)
- [ ] PR title is a valid conventional commit
- [ ] Checks are green
- [ ] Merge method is **Rebase and merge** by default

#### Epic branch → `main`
- [ ] All intended child issues are already merged into the epic
- [ ] Epic checks are green
- [ ] PR title is a valid conventional commit
- [ ] Merge method is chosen intentionally (typically squash only if the PR title is conventional)

### 1. Create Feature Branch

```bash
git checkout -b feature/your-feature-name
```

**Branch naming conventions:**
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Changes

Edit files, test locally, commit:

```bash
# Verify your changes pass tests
make lint
make test

# Commit with descriptive message
git add .
git commit -m "feat: Description of changes

Longer description explaining why this change is needed
and what problem it solves.
"
```

### 3. Push Feature Branch

```bash
git push origin feature/your-feature-name
```

**Note:** You can push to feature branches directly. Only `main` is protected.

### 4. Create Pull Request

1. Visit GitHub.com
2. Click "New Pull Request"
3. Select the correct base branch:
   - child issue work → active epic branch
   - epic completion work → `main`
4. Confirm the header says exactly what you intend, for example:
   - `... into epic/58-sync-contract-hardening from feature/...`
5. Add:
   - Title (must be a conventional commit)
   - Description (why, what, how)
   - Reference any related issues
6. Request review from team members

**Important:** GitHub defaults PR base to `main`. Change it manually whenever the work belongs in an epic first.

### 5. Code Review

**Reviewer checks:**
- ✅ Code quality and style
- ✅ Type hints present
- ✅ Tests included
- ✅ Documentation updated
- ✅ No breaking changes
- ✅ Review checklist completed (`docs/REFERENCE/CODE_REVIEW_CHECKLIST.md`)

**Author responds:**
- Address feedback
- Make requested changes
- Push updates (same branch)
- Mark conversations as resolved

**Copilot review rhythm:**
- Copilot reviews automatically when the PR is opened (GitHub default).
- Push the fix-round commits — Copilot will *not* re-review on each push.
- When the round is complete, re-request review explicitly via the PR UI ("Re-request review" next to Copilot in the Reviewers panel).
- Cap at ~3 rounds; remaining threads roll into a follow-up issue.

### 6. Merge

Once approved:
1. Status checks must pass (lint, test)
2. Click "Merge" on GitHub
3. **DO NOT merge locally** - use GitHub web interface
4. For child issue PRs into an epic, prefer **Rebase and merge**
5. Delete feature branch
6. Artifacts will be automatically deleted

### 7. Cleanup

```bash
git checkout main
git pull origin main
git branch -d feature/your-feature-name
```

---

## Commit Message Format

**All commits MUST follow [Conventional Commits](https://www.conventionalcommits.org/) format.**

This is enforced locally by the `local-commitlint` commit-msg hook and in CI by
`wagoid/commitlint-github-action`, both using `commitlint.config.mjs` as the
single source of truth.

### Format

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types (Required)

- `feat` - New feature
- `fix` - Bug fix
- `refactor` - Code refactoring
- `test` - Test additions/improvements
- `docs` - Documentation
- `chore` - Build, dependencies, etc.
- `style` - Code style changes (formatting, missing semicolons, etc.)
- `perf` - Performance improvements
- `ci` - CI/CD changes
- `revert` - Revert a previous commit

### Scope (Optional)

Short identifier for the area being modified:
- `environment` - Environment/venv changes
- `scripts` - Scripts in `/scripts`
- `docker` - Docker/containerization
- `testing` - Test suite
- `docs` - Documentation

### Subject (Required)

- Use lowercase
- Imperative mood ("add" not "added")
- No trailing period
- Maximum 100 characters
- Should concisely explain what, not why

### Body (Optional)

- Explain **why** this change is needed
- Explain **what** problem it solves
- Separate from subject with blank line
- Wrap at 100 characters
- Reference issues if applicable

### Footer (Optional)

Used for breaking changes and issue references:

```
Closes #123
Fixes #456
BREAKING CHANGE: description of what broke
```

### Examples

```bash
# ✅ Good: Simple feature
git commit -m "feat: add Redis caching layer"

# ✅ Good: Bug fix with body
git commit -m "fix(docker): resolve build timeout

The Docker build was timing out due to slow layer caching.
This change adds layer caching optimizations."

# ✅ Good: Feature with scope and body
git commit -m "feat(environment): add Playwright layer support

Implement layer system to extend base environment with
additional packages for specific use cases. Includes
comprehensive tests and documentation.

Closes #123"

# ❌ Wrong: Missing type
git commit -m "added feature"

# ❌ Wrong: Type not lowercase
git commit -m "Feat: new feature"

# ❌ Wrong: No colon after type
git commit -m "feat new feature"

# ❌ Wrong: Subject too long
git commit -m "feat: this is a very long subject that exceeds the maximum allowed character limit of 100 characters"
```

### Validation

Local commit-message validation uses `commitlint` with `commitlint.config.mjs` as the
single source of truth — the same config used by CI (`wagoid/commitlint-github-action`).
This means a commit message rejected locally will also be rejected in CI, and vice versa.

The `local-commitlint` hook runs `scripts/run_commitlint.sh` at the `commit-msg` stage.
Trailing-period rejection is enforced there as an explicit `subject-full-stop` rule in
`commitlint.config.mjs`; there is no separate local-only subject validator.

The script resolves a runtime in this order:

1. Local `npm` (available inside the project container — preferred)
2. Docker with pinned `@commitlint/cli@19.8.0` + `@commitlint/config-conventional@19.8.0` (host fallback)
3. Hard fail with instructions if neither is available

A working Docker daemon is required when committing outside the project container on a
host without Node/npm installed.

```bash
# Valid commit (accepted)
$ git commit -m "feat: add caching"
✓ Conventional Commit (commitlint) passed

# Invalid commit (rejected)
$ git commit -m "added feature"
✗ subject-empty: subject may not be empty
✗ type-empty: type may not be empty

# Invalid commit: body line too long (also rejected by CI)
$ git commit -m "fix: short subject
>
> $(python3 -c "print('x'*101)")"
✗ body-max-line-length: body's lines must not be longer than 100 characters
```

### Setup

The commit message hook is installed automatically when you run:

```bash
make setup     # Creates environment and installs hooks
make bootstrap # Like setup, but cleans first
make precommit # Re-installs pre-commit hooks (use if hooks get corrupted)
```

---

## Automatic Versioning & Releases

Once your pull request is merged to `main`, the **Release Please** workflow automatically:

1. **Analyzes commits** since the last release
2. **Calculates next version** based on commit types:
   - `feat:` → Minor version bump (0.1.0 → 0.2.0)
   - `fix:` → Patch version bump (0.1.0 → 0.1.1)
   - `BREAKING CHANGE:` → Major version bump (0.1.0 → 1.0.0)
   - `docs:`, `chore:`, `test:`, etc. → **No version bump**
3. **Creates release PR** updating:
   - `VERSION` file
   - `pyproject.toml` version field
   - `CHANGELOG.md` with formatted release notes
4. **Generates GitHub Release** with:
   - Auto-formatted changelog entries
   - Commit links
   - GitHub-generated source archives (no additional built artifacts by default)

### Example Release

**Commits merged to main:**
```
feat(docker): add multi-stage build optimization
fix(environment): resolve Python 3.11 compatibility issue
docs: update README with examples
```

**Automatic result:**
- Version bumped: 0.1.0 → 0.2.0 (minor bump for `feat`)
- Release PR created
- CHANGELOG updated with both `feat` and `fix` entries
- GitHub Release generated with formatted notes

### What This Means

- **Write meaningful commit messages** - they appear in release notes
- **Group related changes in one commit** - improves readability
- **Use `BREAKING CHANGE:` footer for major versions** - don't put in subject
- **Example breaking change commit:**
  ```
  fix: remove deprecated API endpoint

  BREAKING CHANGE: The /api/v1 endpoint is no longer supported.
  Users must migrate to /api/v2 before next release.
  ```

For more details, see `docs/WORKFLOW_AUTOMATION_PLAN.md`.

---

## Release Process

### Version Tags (Immutable)

All version tags (`v1.2.0`, `v1.2.1`, etc.) are **permanently immutable** and should never be retagged or force-pushed. This ensures:
- Audit trails remain intact
- Reproducibility is guaranteed
- Compliance with supply chain security practices

If a release needs correction, create a new patch version (e.g., `v1.2.1`) rather than modifying an existing tag.

### Release/Stable Channel (Moving)

The `release/stable` branch automatically points to the latest release commit and is updated with each new version tag. This provides consumers with a stable, always-current reference without manual version management.

### Release Automation

Releases are automated via `release-please` GitHub Action on the `main` branch:
1. A release PR is created summarizing changes based on conventional commits
2. When merged, `release-please` tags the commit and creates the release
3. Post-release automation updates the `release/stable` branch to point to the new commit
4. Docker image is built and pushed with both major.minor and major.minor.patch tags

---

## Setup

---

## Git Hooks and Branch Protection

Git hooks are automatically installed when you run `make setup` or `make bootstrap`. These hooks prevent direct commits/pushes to `main` and run code quality checks.

**What's included:**
- **Branch protection:** Blocks commits and pushes to `main` branch
- **Code quality:** Runs ruff, black, isort, mypy on Python files
- **Security:** Checks for secrets, private keys, large files
- **Tests:** Validates tests can be collected with pytest

**If you accidentally try to commit to main:**
```bash
$ git commit -m "fix"
❌ Direct commits to main are not allowed. Use a feature branch.
```

**If you accidentally try to push to main:**
```bash
$ git push origin main
❌ Direct pushes to main are not allowed. Use a Pull Request.
```

**Correct workflow:**
```bash
git checkout -b feature/your-feature
git commit -m "feat: your changes"
git push origin feature/your-feature
# Then create a PR on GitHub
```

---

## Development Workflow

### 1. Create the Environment

```bash
scripts/create_env.sh
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
```

### 2. Run Tests

```bash
make test          # Run all tests
make lint          # Run linters
make lint-fix      # Auto-fix linting issues
make verify        # Verify environment integrity
make docs-check    # Validate markdown activation command patterns
```

---

## 🛠️ Makefile Commands Reference

### Environment Setup

```bash
make bootstrap     # Clean slate: remove old env, create new, verify, install pre-commit hooks
make setup         # Create environment, verify, and install pre-commit hooks (recommended)
make env           # Create virtual environment (idempotent - safe to run multiple times)
make clean         # Remove the virtual environment completely
make upgrade       # Force environment recreation and verification (use after dependency changes)
make update-docker # Rebuild and restart Docker container after Dockerfile changes
```

### Development Workflow

```bash
make active        # Show instructions to activate the virtual environment
make verify        # Verify active environment matches repository contract
make test          # Run all pytest tests
make lint          # Run code quality checks (ruff, black, isort, mypy)
make lint-fix      # Auto-fix linting issues (runs ruff --fix, black, isort)
make typecheck     # Run mypy type checking only
```

### Package Management

```bash
make lock          # Pin runtime requirements.txt from a clean env (dev-tool packages excluded)
make upgrade       # Recreate environment and verify (useful after updating dependencies)
```

### Git Hooks

```bash
make precommit     # Install pre-commit hooks (blocks commits to main branch)
```

### Local CI Debugging (act)

```bash
make install-act   # Install act locally to ~/.local/bin (with checksum verification)
```

Run the GitHub Actions build job locally:

```bash
act -j build
```

**Security note:** Installation uses checksum-verified binaries from GitHub releases. See `.github/SUPPLY_CHAIN_SECURITY.md` for details.

If Docker is not running or act is missing, install it with the Make target above.

### Common Workflows

**First time setup:**
```bash
make setup         # Creates env, verifies, installs hooks
make active        # Shows activation command
```

**Daily development:**
```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
make test          # Run tests
make lint-fix      # Fix linting issues automatically
make lint          # Verify all checks pass
```

**Clean rebuild:**
```bash
make bootstrap     # Nuclear option: clean + setup + verify + hooks
```

**After updating dependencies:**
```bash
# Edit requirements.txt
make upgrade       # Force recreate env and verify
make test          # Ensure tests still pass
```

**After Dockerfile changes:**
```bash
make update-docker # Rebuild container to apply Dockerfile changes (e.g., jq install)
```

---

### 3. Make Changes

Edit `scripts/create_env.sh`, `scripts/verify_env.sh`, or metadata files.

### 4. Test Your Changes

```bash
# Test the script directly
scripts/create_env.sh --force
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
scripts/verify_env.sh

# Or run the full test suite
make test
```

### 5. Create Pull Request

See "Pull Request Workflow" section above.

---

## Understanding the Scripts

### `scripts/create_env.sh`

**Purpose:** Create a deterministic virtual environment.

**Flow:**
1. **Pre-flight checks:** Validate all metadata files exist
2. **Parse metadata:** Extract Python version, pip version, environment version
3. **Select interpreter:** Find the correct Python executable
4. **Create venv:** `python -m venv`
5. **Upgrade pip:** Install exact pip version
6. **Install packages:** `pip install -r requirements.txt`
7. **Validate:** Verify pip installation succeeded

**Key features:**
- **Idempotent:** Skips creation if environment exists (`--force` to recreate)
- **Error handling:** Cleanup on failure, detailed error messages
- **Validation:** Checks pip version after installation

**To debug:**
```bash
bash -x scripts/create_env.sh  # Run with trace
```

---

### `scripts/verify_env.sh`

**Purpose:** Validate that an active environment matches the repository contract.

**Flow:**
1. **Pre-flight checks:** Validate metadata files exist
2. **Check activation:** Ensure a virtual environment is active
3. **Python version:** Verify major.minor matches `pyproject.toml`
4. **pip version:** Verify version matches `tooling.toml`
5. **Tools:** Verify required tools (black, ruff, pytest, etc.) are installed
6. **Packages:** Spot-check key packages are installed

**Key features:**
- **Requires activation:** Must be run inside an activated environment
- **Detailed output:** Shows what's being verified
- **Fail fast:** Exits on first mismatch

**To debug:**
```bash
bash -x scripts/verify_env.sh  # Run with trace
```

---

## Test Suite

### File Organization

```
tests/environment/
├── test_metadata_parsing.py      # Metadata file validation (14 tests)
├── test_environment_validation.py # Environment integrity (9 tests)
├── test_create_env.py            # Environment existence (1 test)
└── test_verify_env.py            # Python version matching (1 test)
```

### Test Coverage

**Total:** 25 tests

**Metadata Parsing (14 tests):**
- VERSION file: exists, not empty, semver format
- pyproject.toml: exists, requires-python defined, valid format
- tooling.toml: exists, pip version defined, semver format
- requirements.txt: exists, not empty, all packages have versions, no duplicates

**Environment Validation (9 tests):**
- Environment directory exists, has python/pip binaries
- Python version matches pyproject.toml specification
- pip version matches tooling.toml specification
- Required tools installed (black, isort, ruff, mypy, pytest, pre-commit)
- Sample packages from requirements.txt are installed

**Environment Existence (1 test):**
- Environment directory exists (basic sanity check)

**Python Version (1 test):**
- Python version in environment matches manifest

### Adding New Tests

**Pattern:**
```python
class TestNewFeature:
    """Test description."""

    def test_specific_behavior(self):
        """Test that specific behavior works."""
        # Setup
        # ...

        # Assert
        assert condition, "Error message"
```

**Example: Test new metadata requirement**
```python
class TestRequiredTools:
    """Test that required tools are defined."""

    def test_pytest_in_requirements(self):
        """pytest must be in requirements.txt."""
        with open("requirements.txt") as f:
            content = f.read()
            assert "pytest==" in content, "pytest not in requirements.txt"
```

**Running tests:**
```bash
# All tests
make test

# Specific test file
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && python -m pytest tests/environment/test_metadata_parsing.py -v"

# Specific test
bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && python -m pytest tests/environment/test_metadata_parsing.py::TestVersionFileParsing::test_version_file_exists -v"
```

---

## Modifying Metadata

### Update Python Version

1. **Update pyproject.toml:**
   ```toml
   requires-python = "==3.12.0"
   ```

2. **Update VERSION:**
   ```
   0.2.0
   ```

3. **Recreate environment:**
   ```bash
   scripts/create_env.sh --force
   ```

4. **Verify:**
   ```bash
   REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
   REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
   bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && scripts/verify_env.sh"
   ```

---

### Update pip Version

1. **Update tooling.toml:**
   ```toml
   pip = "25.0.0"
   ```

2. **Update VERSION:**
   ```
   0.1.1
   ```

3. **Recreate environment:**
   ```bash
   scripts/create_env.sh --force
   ```

4. **Verify:**
   ```bash
   REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
   REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
   bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && scripts/verify_env.sh"
   ```

---

### Update Dependencies

1. **Activate environment:**
   ```bash
   REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
   REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
   source ~/envs/"${REPO_NAME}"-env/bin/activate
   ```

2. **Install/upgrade package:**
   ```bash
   pip install --upgrade pytest
   ```

3. **Update requirements.txt:**
   ```bash
   make lock
   ```

4. **Update VERSION:**
   ```
   0.1.2
   ```

5. **Recreate environment:**
   ```bash
   scripts/create_env.sh --force
   ```

6. **Verify:**
   ```bash
   REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
   REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
   bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && scripts/verify_env.sh"
   ```

---

## Common Development Tasks

### Check Environment Status

```bash
# Quick verification
make verify

# Detailed inspection
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
pip list
pip check
```

### Clean Up

```bash
# Remove environment
make clean

# Remove Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

### Run Linters Manually

```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate

ruff check .
black --check .
isort --check-only .
mypy .
```

### Auto-format Code

```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate

black .
isort .
ruff check --fix .
```

---

## Debugging

### Enable Script Trace

```bash
# Trace create_env.sh
bash -x scripts/create_env.sh

# Trace verify_env.sh
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
bash -x scripts/verify_env.sh
```

### Check Metadata Parsing

```bash
# List what create_env.sh reads
cat VERSION
grep requires-python pyproject.toml
grep pip tooling.toml
head requirements.txt
```

### Inspect Environment

```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate

# Python version
python --version

# pip version
pip --version

# Installed packages
pip list

# Check dependencies
pip check

# Verify specific tool
which black
black --version
```

---

## Git Workflow

### Typical commit

```bash
# 1. Make changes
# ... edit scripts, metadata files ...

# 2. Run tests
make test
make lint

# 3. Commit metadata files only
git add pyproject.toml tooling.toml requirements.txt VERSION scripts/
git commit -m "Upgrade dependencies to resolve security issue"

# 4. Push
git push origin main
```

### Things NOT to commit

```
~/envs/           # Environment directory (outside repo)
.venv/            # Never commit virtual environments
__pycache__/      # Python cache
*.pyc             # Python bytecode
.pytest_cache/    # Test cache
*.egg-info/       # Package metadata
```

---

## CI/CD Integration

### GitHub Actions Workflow

The workflow (`.github/workflows/verify-environment.yml`) runs:
1. **verify job:** Create environment and run `verify_env.sh`
2. **lint job:** Run linters (ruff, black, isort)
3. **test job:** Run pytest suite

All jobs cache pip packages for speed.

### Docker Hub auth for CI (optional but recommended)

Some CI steps pull images from Docker Hub (for example Buildx bootstrap images and
Docker-based actions). Unauthenticated pulls can be rate-limited, and repeated
failed logins can temporarily lock runner IPs.

Configure these repository secrets to enable authenticated pulls:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN` (access token, not account password)

Workflows validate that these secrets are provided as a pair. If only one is set,
the job fails fast with a clear error.

### Adding New CI Jobs

**Example: Add mypy type checking**
```yaml
mypy:
  name: Type Check
  runs-on: ubuntu-latest
  needs: verify
  steps:
    - uses: actions/checkout@v4
    - name: Cache pip packages
      uses: actions/cache@v4
      with:
        path: ~/.cache/pip
        key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements.txt') }}
    - name: Create environment
      run: scripts/create_env.sh
    - name: Run mypy
      run: |
        REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
        REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
        bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && mypy ."
```

---

## Best Practices

### For Script Changes

1. **Test in isolation:**
   ```bash
   scripts/create_env.sh --force
   REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
   REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
   bash -lc "source ~/envs/${REPO_NAME}-env/bin/activate && scripts/verify_env.sh"
   ```

2. **Run full test suite:**
   ```bash
   make test
   ```

3. **Document assumptions:**
   - Add comments in scripts for non-obvious logic
   - Update README if behavior changes

### For Metadata Changes

1. **Update VERSION** when anything changes
2. **Test with recreate:**
   ```bash
   scripts/create_env.sh --force
   ```
3. **Always commit metadata files together:**
   ```bash
   git add pyproject.toml tooling.toml requirements.txt VERSION
   ```

### For Test Changes

1. **Test names should describe behavior:**
   ```python
   def test_requires_python_exists(self):  # Good
   def test_parsing(self):                 # Bad - too generic
   ```

2. **Include helpful error messages:**
   ```python
   assert version is not None, f"Could not parse version from {line}"
   ```

---

## Questions?

Refer to:
- `README.md` — User-facing documentation
- `scripts/*.sh` — Implementation details
- `tests/` — Test examples

---

## PyCharm Conventional Commit Plugin

To help ensure all commit messages follow the Conventional Commits standard **before** committing, install the Conventional Commit plugin for PyCharm:

- **Plugin Name:** Conventional Commit
- **Plugin ID:** com.github.lppedd.idea-conventional-commit
- **Plugin URL:** [https://plugins.jetbrains.com/plugin/13389-conventional-commit](https://plugins.jetbrains.com/plugin/13389-conventional-commit)

### Features
- Autocomplete for commit types (feat, fix, docs, etc.)
- Live validation of commit messages
- Integrates with PyCharm's commit dialog
- Shows errors before you commit

### Installation Steps
1. Open **PyCharm**
2. Go to **Settings** → **Plugins**
3. Search for: `Conventional Commit`
4. Click **Install**
5. Restart PyCharm if prompted

**Plugin page:** [Conventional Commit Plugin](https://plugins.jetbrains.com/plugin/13389-conventional-commit)

### Usage
- When committing, use the PyCharm commit dialog.
- The plugin will validate your commit message in real time.
- Errors will be shown if the message does not follow the Conventional Commits format.
- This helps you fix issues before the pre-commit hook runs.

### Screenshots
<!--
Add screenshots here showing:
- Searching for the plugin in the Plugins marketplace
- The install dialog
- The commit dialog with validation/error messages
-->

### Testing
- [ ] Install the plugin in PyCharm
- [ ] Test that commit message validation works
- [ ] Confirm that the pre-commit hook still enforces Conventional Commits

### Notes
- This plugin is **optional** but highly recommended for all contributors using PyCharm.
- It helps catch commit message issues before the commit is created, saving time and avoiding failed commits.
- The pre-commit hook (`conventional-pre-commit`) is still required and will block invalid messages

---

## Issue and Pull Request Templates

To standardize and improve the quality of issues and pull requests, this repository uses GitHub templates for:

- Bug reports
- Feature requests
- Documentation requests
- Pull requests

### Issue Templates

When creating a new issue, select the appropriate template:

- **Bug report:** For reporting problems or unexpected behavior. Fill out steps to reproduce, environment, and logs.
- **Feature request:** For suggesting new features or improvements. Provide a user story and acceptance criteria.
- **Documentation:** For requesting new documentation or reporting unclear/missing docs.

### Pull Request Template

All pull requests must use the provided template, which includes:
- Description and motivation
- Related issues (e.g., Closes #42)
- Testing performed
- Checklist (tests, lint, docs, conventional commits)

See `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE.md` for details.

For more information, see the [GitHub documentation on templates](https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests).

---

## Creating Branches from Issues

To create a properly-named branch from a GitHub issue, use the Makefile target:

```bash
make branch ISSUE=42
```

This will:
- Fetch the issue title and labels using the GitHub CLI (`gh`)
- Generate a branch name in the format `<type>/<id>-<slug>`
  - `type` is determined by labels: `feature` (default), `fix` (if bug), `docs` (if documentation)
  - `id` is the issue number
  - `slug` is a lowercase, hyphenated, alphanumeric version of the title (max 50 chars)
- Create and switch to the new branch

**Requirements:**
- [GitHub CLI (`gh`)](https://cli.github.com/)
- [jq](https://stedolan.github.io/jq/) (now installed in Docker)

**Example:**

```bash
make branch ISSUE=42
# => feature/42-add-redis-caching
```

**Script location:** `scripts/create_branch.sh`

---

## Required Tools

Some scripts require additional tools to be installed in your environment or container:

- **jq**: Command-line JSON processor (required for scripts/create_branch.sh)
  - Install in Ubuntu/Debian: `sudo apt-get install -y jq`
  - Install in Docker: Already included in the Dockerfile
  - Troubleshooting: If you see `jq: command not found`, install jq as above.

---

## Auto-Delete Merged Branches

### GitHub Setting

1. Go to **Repository Settings** → **General**.
2. Scroll to **Pull Requests**.
3. Check: **Automatically delete head branches**.
4. Click **Save**.

GitHub will now automatically delete branches after pull requests are merged.

### Local Cleanup

After branches are deleted on GitHub, you can clean up your local repository:

```bash
# Remove tracking for deleted remote branches
git fetch --prune

# Delete local branches that were merged
git branch --merged main | grep -v main | xargs git branch -d
```

For more details, see the [GitHub documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-branches-in-your-repository/managing-the-automatic-deletion-of-branches).

---

## Tooling Sync

Projects using this repository should run `make sync-tooling` to update shared scripts, hooks, and templates from the separate [tooling repository](https://github.com/jsmithpkp21/tooling).

- Tooling version is pinned in `tooling.toml`.
- **Important:** The command expects the tooling repository to be checked out as a sibling directory at `../tooling`.
- To update tooling, run:
  ```bash
  make sync-tooling TOOLING_VERSION=<version>
  ```
- See the [tooling repository README](https://github.com/jsmithpkp21/tooling) for details and troubleshooting.

### Sync Governance

When a file is shared across repositories, treat `tooling` as the source of truth.

- Change synced scripts, synced docs, `.pre-commit-config.yaml`, and `tooling/pyproject.toml`
  in `tooling` first.
- Keep `.pyproject.meta.toml`, `tooling.toml`, and generated `pyproject.toml` project-local.
- For Python version changes, update `tooling.toml` and let `scripts/merge_pyproject.py`
  regenerate `requires-python`.
- After shared changes merge in `tooling`, run `make sync-tooling` in consumer repos,
  regenerate derived files, and run verification before opening PRs.
- If sync behavior itself changes, update `scripts/sync_tooling.sh` in `tooling` and copy it
  into consumer repos intentionally because it is excluded from normal sync.

See `docs/REFERENCE/PYPROJECT_ARCHITECTURE.md` for the fuller ownership and workflow rules.

## Testing Tooling Sync

- From this repository's root, run `bash ../tooling/tests/test_sync_tooling.sh` to verify `make sync-tooling` works.
- The test checks that the sync-tooling target runs and updates files as expected.
