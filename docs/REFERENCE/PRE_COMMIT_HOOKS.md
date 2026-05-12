# Pre-Commit Hooks - Environment-Agnostic Design

## Overview

This repository uses pre-commit hooks to enforce code quality, security, and branch protection policies. All hooks are designed to work across different environments without assuming specific directory structures or installed tools.

## Design Philosophy

### Enterprise-Scale Requirements

At enterprise scale (tech companies, finance, healthcare), pre-commit hooks must:
1. **Work everywhere**: Dev laptops, CI/CD, containers, different OS
2. **Fail gracefully**: Provide helpful messages when tools are missing
3. **Have fallbacks**: Try multiple sources before giving up
4. **Be fast**: Don't block developers unnecessarily

## Hook Categories

### 1. Branch Protection (Always Runs)

**Purpose:** Enforce feature-branch workflow (no direct commits/pushes to main)

```yaml
- id: block-commits-to-main
  entry: bash -c 'if [ "$(git rev-parse --abbrev-ref HEAD)" = "main" ]; then ...'
  stages: [commit]

- id: block-push-to-main
  entry: bash -c 'protected_branch="main"; while read local_ref ...'
  stages: [push]
```

**Behavior:**
- ✅ Always enforced (required for all users)
- ❌ No fallback (intentionally strict)
- 📝 Clear error messages guide users to create feature branch

### 2. Code Quality (Auto-Fix)

**Purpose:** Enforce style, type hints, imports

```yaml
- Ruff (linting + auto-fix)
- isort (import sorting)
- mypy (type checking)
```

**Behavior:**
- ✅ Runs on all Python files
- ✅ Auto-fixes issues when possible
- ❌ Blocks commit if unfixable errors

### 3. File Validation (Fast Checks)

**Purpose:** Catch common mistakes before commit

```yaml
- check-yaml / check-toml / check-json
- check-merge-conflict
- end-of-file-fixer
- trailing-whitespace
- check-added-large-files
- detect-private-key
```

**Behavior:**
- ✅ Runs on all file types
- ✅ Auto-fixes formatting issues
- ❌ Blocks commit if secrets/large files detected

### 4. Markdown Lint (No Bare URLs)

> **Runtime policy:** This hook follows the repo-family local-tooling runtime
> policy — local binary first, pinned Docker fallback second, hard-fail with
> remediation otherwise. The policy and its required invariants are documented
> in [ADR-0001](adr/0001-local-tooling-runtime-policy.md). The same pattern
> applies to `scripts/run_commitlint.sh`.

**Purpose:** Enforce consistent Markdown link style; bare URLs must be wrapped as
Markdown links `[text](url)` in prose.

**Rule enabled:** `MD034` (no-bare-urls)

```yaml
- repo: local
  hooks:
    - id: markdown-lint
      name: markdown-lint
      entry: make markdown-lint
      language: system
      pass_filenames: false
      stages: [commit, push]
```

**Behavior:**
- ✅ Runs at commit and push via `make markdown-lint`
- ✅ Lints **tracked** Markdown files only (`git ls-files '*.md'`)
- ✅ Uses local `markdownlint` binary when available (e.g. inside the project container)
- ✅ Falls back to Docker with pinned `markdownlint-cli@0.47.0` when local binary is absent
- ❌ Fails when a bare URL is found outside code contexts
- ❌ Fails if neither `markdownlint` nor Docker is available

**Runtime resolution order:**
1. Local `markdownlint` binary (present inside project container - preferred path)
2. Docker with pinned `node:20-bullseye` + `npx markdownlint-cli@0.47.0` (host fallback)
3. Hard fail with actionable instructions if fallback runtime is unavailable

**Docker requirement (host fallback only):**
A working Docker daemon must be available when using the Docker fallback outside
the project container (for example, Docker Engine on Linux/macOS, or Docker
Desktop on Windows).

```bash
docker info  # verify Docker daemon access
```

> Optional Windows/WSL2 note: if Docker Desktop is used from WSL, enable WSL
> integration for this distro.

**Allowed exceptions:**

| Context | Exempt? | Reason |
|---------|---------|--------|
| Fenced code block (`\`\`\``) | ✅ Yes | markdownlint skips code content |
| Inline code span (`` ` `` ) | ✅ Yes | markdownlint skips code content |
| Prose / list / heading | ❌ No | Must use `[label](url)` |

To suppress a **single line** (rare, must be justified in code review):

```markdown
<!-- markdownlint-disable-next-line MD034 -->
https://example.com
```

**Running manually:**

```bash
make markdown-lint
# or
make markdown-lint-docker
```


### 5. Test Collection (Environment-Agnostic) ⭐

**Purpose:** Verify tests can be collected (syntax check)

```yaml
- id: pytest-collect
  entry: bash -c 'REPO_NAME=$(git remote get-url origin 2>/dev/null | sed "s|.*/||; s|\.git$||");
                  REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}";
                  ENV_PATH="$HOME/envs/${REPO_NAME}-env";
                  if [ -f "$ENV_PATH/bin/activate" ]; then
                    source "$ENV_PATH/bin/activate" && pytest --collect-only;
                  elif command -v pytest >/dev/null 2>&1; then
                    pytest --collect-only;
                  else
                    echo "⚠️  pytest not found (run make setup)" && exit 0;
                  fi'
```

**Fallback Chain:**
1. **Try project venv:** `~/envs/<repo-name>-env` (name derived from git remote)
2. **Try system pytest:** If `pytest` command exists
3. **Skip gracefully:** Print warning, allow commit

**Behavior:**
- ✅ Works for new contributors (before `make setup`)
- ✅ Works in CI (uses system pytest)
- ✅ Works with custom env paths (uses system fallback)
- ⚠️ Only warns if pytest unavailable (doesn't block commit)

**Why This Matters at Scale:**
- Developers use Windows, Linux, macOS
- CI uses containerized pytest (different paths)
- Embedded teams may use custom Python installations
- Pre-commit hooks must not assume a specific setup

### 6. Documentation Command Pattern Check ⭐

**Purpose:** Prevent fragile activation snippets in markdown docs.

```bash
python3 scripts/validate_activation_commands.py --root .
# or
make docs-check
```

**What it flags:**
- `source ~/envs/$(git remote get-url origin ...)-env/bin/activate`
- `bash -lc "source ~/envs/$(git remote get-url origin ...)-env/bin/activate && ..."`

**Why this exists:**
- Inline command substitution can produce an empty repo name when `origin` is missing.
- The robust two-step fallback pattern avoids `~/envs/-env` activation failures.

**Required robust pattern:**
```bash
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
```

### 7. Workflow Action Pin Policy

**Purpose:** Keep CI workflows deterministic and lock-validated.

**Policy:** External actions in `.github/workflows/*.yml` must use strict semver tags (`@vX.Y.Z`).
Floating majors (for example `@v4`) are not allowed.

**Enforcement commands:**

```bash
make action-pin-check
make action-pin-fix
```

`action-pin-check` validates exact matches against `.github/workflow-action-lock.json`.
`action-pin-fix` rewrites mismatched `uses:` refs to the locked values.

## Installation

### First-Time Setup

```bash
make setup
# Or manually:
REPO_NAME="$(git remote get-url origin 2>/dev/null | sed 's|.*/||; s|\.git$||')"
REPO_NAME="${REPO_NAME:-$(basename "$(git rev-parse --show-toplevel 2>/dev/null || pwd)")}"
source ~/envs/"${REPO_NAME}"-env/bin/activate
pre-commit install --hook-type pre-commit --hook-type pre-push
```

### Testing Hooks

```bash
# Test all hooks on staged files
pre-commit run

# Test all hooks on all files
pre-commit run --all-files

# Test specific hook
pre-commit run pytest-collect --all-files
```

## Troubleshooting

### Hook Fails: "pytest not found"

**Symptom:**
```
⚠️  pytest not found (run make setup to create environment)
```

**Solution:**
```bash
make setup  # Creates environment and installs pytest
```

**Alternative (skip for now):**
```bash
pip install pytest  # System-level install
```

### Hook Fails: "Virtual environment not found"

**Symptom:**
```
source: ~/envs/<repo-name>-env/bin/activate: No such file or directory
```

**Solution:**
This should never happen with the new environment-agnostic hooks. If it does:
1. Check VERSION file exists: `cat VERSION`
2. Verify hook uses fallback logic: `cat .pre-commit-config.yaml | grep pytest-collect`
3. Report bug if hook doesn't fall back to system pytest

### Hook Fails: "mypy/ruff/isort not found"

**Solution:**
```bash
make setup  # Installs all dev tools
```

## Customization

### Disable Specific Hook (Not Recommended)

```bash
SKIP=mypy pre-commit run
```

### Skip All Hooks (Emergency Only)

```bash
git commit --no-verify -m "emergency fix"
```

**Warning:** Branch protection hooks will still block pushes to main.

## Interview Talking Points

**When asked about pre-commit hooks:**

✅ **Environment-agnostic design:**
- "Hooks gracefully handle missing environments with fallback chains"
- "Works for new contributors before they run setup"
- "CI uses system pytest, developers use project venv - both work"

✅ **Enterprise-scale considerations:**
- "Hooks assume nothing about directory structure or installed tools"
- "Fail with helpful messages, not cryptic errors"
- "Branch protection always enforced, quality checks have fallbacks"

✅ **Testing strategy:**
- "pytest --collect-only is fast (syntax check, not full suite)"
- "Catches import errors and test syntax before CI runs"
- "Doesn't block workflow if pytest unavailable"

## Related Documentation

- **Local Tooling Runtime Policy (ADR-0001):** [`adr/0001-local-tooling-runtime-policy.md`](adr/0001-local-tooling-runtime-policy.md) — canonical decision record for the local-first / Docker-fallback resolution pattern used by this hook and `scripts/run_commitlint.sh`.
- **Branch Protection:** [`docs/REFERENCE/BRANCH_PROTECTION.md`](BRANCH_PROTECTION.md) — branch protection policy and setup notes.
- **Contributing Guide:** `CONTRIBUTING.md`

## Change Log

### 2026-02-18: Environment-Agnostic Pytest Hook
- **Changed:** `pytest-collect` hook from hardcoded path to fallback chain
- **Reason:** Support new contributors, CI environments, custom setups
- **Impact:** Hook now works in all environments without modification
