# Manifesto: Deterministic Python Environments

## Our Vision

Python environments should be **reproducible, auditable, and transparent**—not mysterious, fragile, or tied to hidden state.

We reject:
- ❌ "Works on my machine" problems
- ❌ Silent environment drift
- ❌ Hidden lock files and external tool complexity
- ❌ Environments that break between commits
- ❌ Undocumented dependencies on CI/CD tooling
- ❌ Implicit activation and automatic environment loading

We embrace:
- ✅ Deterministic, reproducible environments
- ✅ Immediate drift detection
- ✅ Plain bash scripts and human-readable metadata
- ✅ Decentralized, project-owned configuration
- ✅ Explicit, deliberate activation
- ✅ Fast, efficient iteration

---

## Core Beliefs

### 1. **Deterministic**
Every environment is created from the same metadata, producing identical results everywhere—laptop, CI/CD, production, team member's machine.

**Implementation:** Metadata files (`pyproject.toml`, `tooling.toml`, `requirements.txt`, `VERSION`) drive all environment creation. Same inputs always produce same outputs.

---

### 2. **Reproducible**
Any developer can recreate any historical environment by checking out any git commit and running `make setup`.

**Implementation:** All versions are pinned exactly. Environment version (`VERSION` file) changes when anything changes. No approximation, no "close enough."

---

### 3. **Auditable**
Drift is detected immediately, not discovered months later in production.

**Implementation:** `verify_env.sh` validates that the active environment matches the contract. Python version, pip version, and installed packages are checked. Mismatches fail loudly.

---

### 4. **Transparent**
Scripts are plain bash. Metadata is human-readable TOML. Configuration is explicit and visible.

**Implementation:** No magic, no hidden lock files, no external tool dependencies beyond standard bash and Python. `cat` the metadata files to understand everything.

---

### 5. **Decentralized**
Each project owns its environment metadata. Multiple projects coexist without collisions or interference.

**Implementation:** Environments live in `~/envs/<repo-name>-env` keyed by repository name. Multiple projects coexist without collisions or interference.

---

### 6. **Explicit**
Environment activation is always a deliberate user action, never automatic or implicit.

**Implementation:** Scripts never auto-activate. `source` activation is always typed by the user or explicitly requested in a shell command. Developers always know which Python they're using.

---

### 7. **Minimal**
Built on Python's standard `venv`. No external tools, no lock file formats, no package manager alternatives.

**Implementation:** Uses `python -m venv` for environment creation and `pip` for package installation. Works anywhere bash and Python 3.3+ work—no additional dependencies.

---

### 8. **Fast**
Idempotent creation means second runs take ~1 second. CI/CD caching means fast feedback in pipelines.

**Implementation:** `create_env.sh` checks if environment exists and skips recreation. `--force` flag available for when recreation is needed. Git-aware CI/CD caching speeds up repeated runs.

---

### 9. **Testable**
25+ tests validate metadata parsing, environment structure, version matching, and package installation.

**Implementation:** Comprehensive test suite ensures no regressions. All critical paths covered. Drift is caught by tests before deployment.

---

### 10. **Resilient**
Failures are caught early with clear error messages. Partial state is cleaned up automatically.

**Implementation:** Pre-flight validation, error traps, automatic cleanup on failure. When something goes wrong, the error message tells you exactly what and why.

---

## Principles

### Single Source of Truth
Each piece of information lives in exactly one place:
- **Python version** → `pyproject.toml`
- **pip version** → `tooling.toml`
- **Packages** → `requirements.txt`
- **Environment version** → `VERSION`

No duplication. No inconsistency.

### Deterministic Creation
`create_env.sh` reads metadata and builds an environment that exactly matches the contract.
- Same inputs → Same outputs, every time
- Idempotent: Safe to run multiple times
- Pre-flight validation catches errors early
- Automatic cleanup on failure

### Self-Auditing Verification
`verify_env.sh` validates the active environment against the contract.
- Catches drift immediately
- Makes problems visible and actionable
- Fails loudly with clear messages
- Part of routine workflows (`make verify`, CI/CD)

### Explicit Activation
Scripts never auto-activate environments.
- Activation is always a deliberate user action
- `source ~/envs/<repo-name>-env/bin/activate`
- Developers know exactly when they're using which Python
- No hidden state transitions

---

## Workflow Philosophy

### Development
```bash
make setup        # Create and verify environment
make active       # See activation instructions
source ...        # Activate when ready
make test         # Run tests
make lint         # Check code quality
```

### Collaboration
- Commit metadata files (`pyproject.toml`, `tooling.toml`, `requirements.txt`, `VERSION`)
- Never commit environment directories (`~/envs/`)
- Teammates run `make setup` to get identical environment
- Zero coordination needed—metadata is single source of truth

### Updates
1. **Update Python:** Edit `pyproject.toml`, increment `VERSION`
2. **Update pip:** Edit `tooling.toml`, increment `VERSION`
3. **Update packages:** Run `pip install ...`, then `make lock`, increment `VERSION`
4. **Test:** Run `make setup && make test && make lint`
5. **Commit:** All metadata files together
6. **CI/CD:** Automatic verification on every push

### CI/CD Integration
- GitHub Actions runs `make verify`, `make lint`, `make test` automatically
- Pip caching speeds up repeated runs (10-15 seconds typical)
- Failures are visible in PR checks
- Same environment as local development

---

## Anti-Patterns We Reject

### ❌ Hidden Lock Files
Lock files are opaque. We use explicit `requirements.txt` with exact pins.

### ❌ External Tool Dependencies
Poetry, uv, pipenv add complexity. We use standard `venv` and `pip`.

### ❌ Auto-Activation
`.env` files and shell hooks are magical. We require explicit `source` commands.

### ❌ Implicit Versions
"Python 3.11 or higher" is vague. We pin exact versions: `==3.11.14`.

### ❌ Unaudited State
Drifting environments are found in production. We audit constantly.

### ❌ Monolithic Monorepos
Shared environments conflict. We use versioned, project-specific environments.

---

## Design Decisions

### Why `~/envs/` Outside the Repository?
- Environments are large and platform-specific
- Git doesn't track binary packages efficiently
- Team members can have different system Python versions
- Environments can be deleted and recreated from metadata

### Why Pin Exact Versions?
- Determinism requires no approximation
- `pip freeze` captures exact state
- Reproducing historical environments requires exact versions
- Patch version differences can matter (especially for security)

### Why Separate `VERSION` File?
- Single version identifier for entire environment
- Changes to any metadata (Python, pip, packages) require version bump
- Prevents accidental reuse of stale environments

### Why `verify_env.sh` After Creation?
- Catch installation failures immediately
- Validate environment matches contract
- Spot-check critical packages
- Fail fast if something is wrong

### Why Make Targets?
- Memorable, self-documenting commands
- Works in any shell
- No extra tool dependencies
- Consistent with industry standards

---

## Success Metrics

We succeed when:

1. ✅ **Determinism:** Every environment is identical
2. ✅ **Reproducibility:** Any historical commit recreates correctly
3. ✅ **Auditability:** Drift is detected before problems occur
4. ✅ **Transparency:** Anyone understands the system by reading files
5. ✅ **Speed:** Second runs take ~1 second, CI/CD runs cache effectively
6. ✅ **Reliability:** No surprises, no hidden state
7. ✅ **Simplicity:** New team members understand it in minutes
8. ✅ **Testability:** 100% of critical paths have test coverage
9. ✅ **Maintainability:** No external tool churn, stable over years

---

## Philosophy in Practice

### Example: Adding a New Package

**Traditional approach:**
```bash
pip install pytest
# Now pytest is installed, but requirements.txt is stale
# Other developers don't get it automatically
# CI/CD might still be testing without pytest
```

**Our approach:**
```bash
pip install pytest           # Install it
make lock                    # Update requirements.txt from pip freeze
# Edit VERSION to bump version (0.1.0 → 0.1.1)
git add pyproject.toml tooling.toml requirements.txt VERSION
git commit -m "Add pytest"
# Teammates: make setup → identical environment with pytest
# CI/CD: Automatic verification that pytest is installed
```

### Example: Updating Python Version

**Traditional approach:**
```bash
# Someone installs Python 3.12
# Maybe they update .python-version or .tool-versions
# Maybe they forget
# Now half the team is on 3.11, half on 3.12
# Bugs appear that only affect one version
```

**Our approach:**
```bash
# Edit pyproject.toml: requires-python = "==3.12.0"
# Edit VERSION: 0.2.0
make setup  # Fails if Python 3.12 not installed (clear error)
# Install Python 3.12, try again
make setup  # Now works, all tests pass
git commit
# CI/CD: Verify Python 3.12 environment works
# Teammates: make setup → immediately get Python 3.12
```

### Example: Investigating Environment Mismatch

**Traditional approach:**
```bash
# "Tests pass locally but fail in CI/CD"
# Debug for hours trying to figure out what's different
# Maybe it's Python version, maybe pip version, maybe a package
# Eventually someone says "did you try deleting and recreating everything?"
```

**Our approach:**
```bash
make verify
# Output shows exactly what's different:
# "ERROR: Python version mismatch: expected 3.11.14, found 3.11.13"
# Fix: Recreate environment or update metadata
make setup  # Fixes it
```

---

## Conclusion

Deterministic Python environments are possible without external tool complexity. By embracing single source of truth, explicit activation, and continuous verification, we build environments that are reproducible, auditable, and transparent.

This is how platform engineering teams should build Python environments.
