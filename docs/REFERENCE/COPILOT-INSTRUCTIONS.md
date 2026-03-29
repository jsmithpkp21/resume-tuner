# Copilot Instructions for Deterministic Python Environment

## ⚠️ CRITICAL RULE #1: NEVER COMMIT WITHOUT EXPLICIT PERMISSION ⚠️

**YOU MUST WAIT FOR THE USER TO SAY "commit" BEFORE COMMITTING ANYTHING.**

- ❌ DO NOT use `git commit` unless the user explicitly tells you to
- ❌ DO NOT commit after making changes
- ❌ DO NOT commit as a final step
- ❌ DO NOT assume the user wants changes committed
- ✅ ONLY commit when the user explicitly says: "commit these changes", "commit this", "please commit", etc.

**If you commit without permission, you are violating the user's explicit instructions.**

---

## Overview
This project uses strict coding standards, comprehensive testing, and deterministic environments. These instructions ensure Copilot generates code that matches project standards on the first attempt.

---

## 🎯 Coding Standards

### Type Hints (MANDATORY)
- **All function signatures must have type hints**
- **All return types must be explicit**
- **All variable types must be annotated** (especially in loops, comprehensions)

**Example - CORRECT:**
```python
def create_environment(repo_name: str, python_path: str) -> bool:
    """Create virtual environment and return success status."""
    env_path: str = os.path.expanduser(f"~/envs/{repo_name}-env")
    configs: dict[str, str] = {"python": python_path, "repo": repo_name}
    return install_packages(env_path, configs)
```

**Example - INCORRECT (don't do this):**
```python
def create_environment(repo_name, python_path):  # Missing type hints
    env_path = os.path.expanduser(f"~/envs/{repo_name}-env")
    configs = {}  # Missing type annotation
    return install_packages(env_path, configs)
```

### Docstrings (MANDATORY)
- Use **Google-style docstrings** for all functions, classes, and modules
- Include description, Args, Returns, Raises sections
- One-liners for simple functions are acceptable

**Example:**
```python
def validate_metadata(path: str) -> tuple[bool, str]:
    """Validate metadata file format and content.

    Args:
        path: Path to metadata file (TOML or JSON).

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty string.

    Raises:
        FileNotFoundError: If metadata file does not exist.
        ValueError: If metadata format is invalid.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Metadata file not found: {path}")

    try:
        with open(path) as f:
            data = tomllib.load(f)
        return True, ""
    except Exception as e:
        return False, str(e)
```

### Code Style (PEP 8 + Project Standards)

**Line length:** 88 characters (Black default)
```python
# CORRECT - lines wrap at 88 chars
very_long_function_call_with_many_parameters(
    param1="value1",
    param2="value2",
    param3="value3"
)

# INCORRECT - line too long
very_long_function_call_with_many_parameters(param1="value1", param2="value2", param3="value3")
```

**Imports:** Follow isort format
```python
# CORRECT order: stdlib, then third-party, then local
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import tomllib

from scripts.utils import validate_config
```

**Naming conventions:**
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `SCREAMING_SNAKE_CASE`
- Private: Prefix with `_` (e.g., `_internal_function`)
- Protected: Double underscore prefix for name mangling (sparingly)

```python
class EnvironmentValidator:
    """Validate environment against contract."""

    DEFAULT_TIMEOUT: int = 300
    _internal_cache: dict[str, bool] = {}

    def validate_python_version(self, version: str) -> bool:
        """Check if Python version matches specification."""
        pass
```

---

## 🧪 Testing Requirements

### Test File Naming
- Test files: `test_<feature>.py`
- Test classes: `Test<Feature>`
- Test methods: `test_<scenario>`

**Example:**
```python
# File: tests/environment/test_metadata_parsing.py

class TestMetadataParsing:
    """Test metadata file parsing."""

    def test_version_file_exists(self) -> None:
        """Verify VERSION file exists."""
        pass

    def test_version_file_not_empty(self) -> None:
        """VERSION file must not be empty."""
        pass
```

### Test Coverage
- **All public functions must have tests**
- **All error paths must be tested**
- **Edge cases must be tested**
- **Minimum 80% code coverage required**

### Test Structure
```python
def test_descriptive_scenario_name(self) -> None:
    """One-line description of what is being tested."""
    # Setup
    input_data: dict[str, str] = {"key": "value"}
    expected: bool = True

    # Execute
    result: bool = function_under_test(input_data)

    # Assert
    assert result == expected, "Clear error message explaining mismatch"
```

### Error Messages
```python
# CORRECT - clear, actionable message
assert version in output, (
    f"Python version mismatch: expected {expected_version}, got {actual_version}"
)

# INCORRECT - unclear
assert version in output, "Version check failed"
```

---

## 📋 Linting Standards

All code must pass these checks **without warnings**:

### Ruff Configuration (enforced in pyproject.toml)
- Line length: 88
- Target: Python 3.11+
- Selected rules: E, F, W, I, B, UP
- Ignored: E501 (long lines, handled by Black)

**Common issues to avoid:**
```python
# ❌ WRONG - Unused import
import os

# ❌ WRONG - Unused variable
result = expensive_function()

# ❌ WRONG - Undefined name
print(undefined_variable)

# ✅ CORRECT - Used imports/variables
import os
env_path = os.path.expanduser("~/envs")
```

### Black Configuration (code formatter)
- Line length: 88
- Target version: Python 3.11
- String normalization: off (`skip-string-normalization = false`)

**Formatting style:**
```python
# ✅ CORRECT - Black format
def function_with_many_parameters(
    param1: str,
    param2: int,
    param3: bool = True,
) -> dict[str, any]:
    """Function description."""
    return {"param1": param1, "param2": param2}

# ❌ WRONG - Not properly formatted
def function_with_many_parameters(param1: str, param2: int, param3: bool = True) -> dict[str, any]:
    return {"param1": param1, "param2": param2}
```

### Isort Configuration (import sorting)
- Profile: black
- Line length: 88
- Multi-line mode: 3 (vertical hanging indent)

**Import organization:**
```python
# ✅ CORRECT - Organized by stdlib, third-party, local
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import tomllib

from .utils import helper_function
```

### Mypy Configuration (type checking)
- Python version: 3.11
- Warn unused configs: true
- Warn unused ignores: true
- Warn redundant casts: true
- Warn return any: true
- Disallow untyped defs: true
- Disallow incomplete defs: true

**Type compliance:**
```python
# ✅ CORRECT - All types specified
def process_data(items: list[str]) -> dict[str, int]:
    """Process items and return counts."""
    result: dict[str, int] = {}
    for item in items:
        result[item] = len(item)
    return result

# ❌ WRONG - Incomplete types
def process_data(items):  # Missing type hint
    result = {}  # Missing annotation
    for item in items:
        result[item] = len(item)
    return result
```

---

## 📁 File Naming Conventions

### Python Files
- Module files: `lowercase_with_underscores.py`
- Test files: `test_<feature>.py`
- Script files: `descriptive_action.py` (e.g., `create_env.sh`, `verify_env.sh`)

### Documentation Files
- Markdown: `UPPERCASE.md` for project docs (README.md, CONTRIBUTING.md, MANIFESTO.md)
- Config files: `lowercase.toml`, `lowercase.txt`

**Examples:**
```
✅ CORRECT:
- tests/environment/test_metadata_parsing.py
- scripts/create_env.sh
- src/environment_manager.py
- README.md
- pyproject.toml

❌ WRONG:
- tests/TestMetadataParsing.py  (class name, not file name)
- scripts/CreateEnv.sh  (capital letters)
- src/EnvironmentManager.py  (class name, not file name)
- readme.md  (should be README.md)
```

---

## 🔄 Code Organization

### Function/Method Order in Classes
1. `__init__` and special methods
2. Public methods
3. Private methods (prefix with `_`)
4. Class methods (if any)
5. Static methods (if any)

```python
class EnvironmentManager:
    """Manage Python environments."""

    def __init__(self, version: str) -> None:
        """Initialize environment manager."""
        self.version: str = version

    def create(self) -> bool:
        """Create environment."""
        return self._setup_venv() and self._install_packages()

    def verify(self) -> bool:
        """Verify environment matches contract."""
        return self._check_python() and self._check_packages()

    def _setup_venv(self) -> bool:
        """Internal: Setup virtual environment."""
        pass

    def _install_packages(self) -> bool:
        """Internal: Install packages from requirements."""
        pass

    def _check_python(self) -> bool:
        """Internal: Check Python version."""
        pass

    def _check_packages(self) -> bool:
        """Internal: Check installed packages."""
        pass
```

### Error Handling

**Always use specific exceptions:**
```python
# ✅ CORRECT - Specific exceptions
try:
    result = subprocess.run(
        ["python", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
except FileNotFoundError:
    raise EnvironmentError("Python executable not found")
except subprocess.TimeoutExpired:
    raise EnvironmentError("Python version check timed out")
except Exception as e:
    raise EnvironmentError(f"Unexpected error checking Python: {e}") from e

# ❌ WRONG - Bare except or too generic
try:
    result = subprocess.run(["python", "--version"])
except:  # Bare except
    pass
except Exception:  # Too generic
    pass
```

**Always provide context in error messages:**
```python
# ✅ CORRECT - Clear, actionable errors
if not os.path.exists(env_path):
    raise FileNotFoundError(
        f"Environment not found at {env_path}. "
        f"Run 'make setup' to create it."
    )

# ❌ WRONG - Unclear errors
if not os.path.exists(env_path):
    raise FileNotFoundError("File not found")
```

---

## 🎨 Code Patterns to Avoid

### ❌ Don't Use
```python
# Bad: Bare string operations
version = "3.11.14"
parts = version.split(".")

# Bad: Untyped loops
for item in items:
    process(item)

# Bad: No docstrings
def validate(x):
    return x > 0

# Bad: Catching all exceptions
try:
    something()
except:
    pass

# Bad: Mutable default arguments
def function(items=[]):
    items.append(1)
    return items

# Bad: String concatenation in loops
result = ""
for item in items:
    result += item  # Inefficient

# Bad: Complex comprehensions without clarity
result = [x.strip().upper() for x in lines if len(x) > 0 and not x.startswith("#")]
```

### ✅ Do Use
```python
# Good: Use dataclasses or typed variables
version: str = "3.11.14"
major, minor, patch = version.split(".")

# Good: Type hints everywhere
for item in items:
    result: bool = process(item)

# Good: Clear docstrings
def validate(x: int) -> bool:
    """Check if value is positive."""
    return x > 0

# Good: Specific exception handling
try:
    something()
except ValueError as e:
    logger.error(f"Invalid value: {e}")
except TimeoutError:
    logger.error("Operation timed out")

# Good: Immutable default arguments
def function(items: list[str] | None = None) -> list[str]:
    """Process items."""
    if items is None:
        items = []
    items.append("1")
    return items

# Good: Use join() for concatenation
result: str = "".join(item for item in items)

# Good: Break down complex comprehensions
filtered_items: list[str] = [
    line.strip().upper()
    for line in lines
    if line and not line.startswith("#")
]
```

---

## 📚 Project-Specific Standards

### Metadata Handling
- Always validate metadata files before reading
- Use `tomllib` (Python 3.11+) for TOML files
- Handle missing keys gracefully with defaults
- Provide helpful error messages for invalid metadata

```python
def read_version() -> str:
    """Read environment version from VERSION file.

    Returns:
        Version string (e.g., "0.1.0").

    Raises:
        FileNotFoundError: If VERSION file doesn't exist.
        ValueError: If VERSION file is empty.
    """
    version_file: str = "VERSION"

    if not os.path.exists(version_file):
        raise FileNotFoundError(f"VERSION file not found at {version_file}")

    with open(version_file) as f:
        version: str = f.read().strip()

    if not version:
        raise ValueError("VERSION file is empty")

    return version
```

### Shell Script Handling
- Use subprocess with proper argument lists (not shell=True)
- Always capture output for logging
- Handle errors explicitly
- Use timeouts to prevent hanging

```python
def run_shell_command(command: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Execute shell command and return status and output.

    Args:
        command: Command as list (e.g., ["pip", "install", "pytest"]).
        timeout: Maximum execution time in seconds.

    Returns:
        Tuple of (success, output_or_error).
    """
    try:
        result: subprocess.CompletedProcess = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.returncode != 0:
            return False, result.stderr

        return True, result.stdout

    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return False, f"Command not found: {command[0]}"
    except Exception as e:
        return False, f"Unexpected error: {e}"
```

---

## 🔍 Pre-Commit Checklist for Generated Code

Before finalizing any generated code, ensure:

- ✅ **Type hints:** All functions have parameter and return types
- ✅ **Docstrings:** All public functions/classes have Google-style docstrings
- ✅ **Tests:** All public functions have corresponding tests
- ✅ **Error handling:** All error paths are handled with specific exceptions
- ✅ **Logging:** Important operations are logged with context
- ✅ **Naming:** Functions/variables use snake_case, classes use PascalCase
- ✅ **Line length:** No lines exceed 88 characters
- ✅ **Imports:** Organized by stdlib, third-party, local
- ✅ **No unused:** No unused imports, variables, or parameters
- ✅ **Formatting:** Follows Black style (verified by running `make lint`)

---

## 🛠️ Common Generation Patterns

### Pattern: Configuration Validation
```python
def validate_config(config_path: str) -> dict[str, str]:
    """Validate and load configuration file.

    Args:
        config_path: Path to configuration file.

    Returns:
        Validated configuration dictionary.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        ValueError: If config is invalid.
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}. "
            f"Please create it with required settings."
        )

    with open(config_path) as f:
        config: dict[str, str] = tomllib.load(f)

    required_keys: list[str] = ["python_version", "pip_version"]
    missing: list[str] = [k for k in required_keys if k not in config]

    if missing:
        raise ValueError(
            f"Configuration missing required keys: {', '.join(missing)}"
        )

    return config
```

### Pattern: Version Comparison
```python
def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse semantic version string.

    Args:
        version_str: Version string (e.g., "3.11.14").

    Returns:
        Tuple of (major, minor, patch).

    Raises:
        ValueError: If version format is invalid.
    """
    try:
        parts: list[str] = version_str.split(".")
        if len(parts) != 3:
            raise ValueError()
        return tuple(int(p) for p in parts)  # type: ignore
    except (ValueError, IndexError):
        raise ValueError(
            f"Invalid version format: {version_str}. "
            f"Expected format: major.minor.patch (e.g., 3.11.14)"
        )
```

### Pattern: Environment Variable Reading
```python
def get_env_var(key: str, default: str | None = None) -> str:
    """Get environment variable with optional default.

    Args:
        key: Environment variable name.
        default: Default value if variable not set.

    Returns:
        Environment variable value or default.

    Raises:
        ValueError: If variable not set and no default provided.
    """
    value: str | None = os.environ.get(key)

    if value is None:
        if default is not None:
            return default
        raise ValueError(
            f"Required environment variable not set: {key}"
        )

    return value
```

---

## 📞 Quick Reference: Before Generating Code

**Ask yourself:**
1. Do all functions have type hints? ✅
2. Do all functions have docstrings? ✅
3. Are there tests for this? ✅
4. Are error messages clear and helpful? ✅
5. Will this pass `make lint`? ✅
6. Are all imports organized correctly? ✅
7. Are names snake_case/PascalCase as appropriate? ✅
8. Is the code under 88 characters per line? ✅

If any answer is "no", regenerate with corrections.

---

## 🔐 Git Commits (CRITICAL)

**NEVER commit changes unless explicitly instructed to do so.**

This is critical for maintaining control over the repository:

### When TO Commit
Only when the user explicitly says:
- "commit these changes"
- "commit the changes"
- "commit this"
- "please commit"
- Any other clear instruction to commit

### When NOT TO Commit
❌ DO NOT commit automatically
❌ DO NOT commit after making changes
❌ DO NOT commit as a "cleanup" step
❌ DO NOT assume the user wants changes committed

### What TO Do Instead
✅ Make the changes
✅ Show what was done
✅ Leave files in staging area or modified state
✅ Wait for explicit commit instruction
✅ When instructed, then commit with clear message

### Example Flow

User: "Add a new feature X"
1. You: Create the code
2. You: Test it works
3. You: Show "Feature X added" (no commit)
4. User: "Looks good"
5. User: "Commit these changes"
6. You: Now you commit

### Branch Protection Enforcement
This project uses:
- **Pre-commit hooks** - Block commits to main
- **Pre-push hooks** - Block pushes to main
- **GitHub branch protection** - Require PR + code review

All changes must go through:
1. Feature branch
2. Pull request
3. Code review approval
4. Merge via GitHub

Committing without instruction defeats this workflow.

---

## Summary

Follow these standards and Copilot will generate production-ready code that:
- ✅ Passes all linting checks on first attempt
- ✅ Has proper type hints throughout
- ✅ Includes comprehensive docstrings
- ✅ Follows project naming conventions
- ✅ Has complete error handling
- ✅ Is thoroughly tested
- ✅ Matches team coding standards
- ✅ Requires no fixes or rewrites
- ❌ **NEVER commits without explicit "commit" instruction from user**

**Goal:** Generate code once, use it immediately. No iteration needed.

---

## ⚠️ FINAL REMINDER: DO NOT COMMIT WITHOUT PERMISSION ⚠️

Before completing any task, ask yourself:

**"Did the user explicitly tell me to commit?"**
- ✅ YES → User said "commit these changes" or similar → Commit is OK
- ❌ NO → User did NOT say "commit" → DO NOT COMMIT

**STOP. READ THE USER'S REQUEST AGAIN. Did they say "commit"?**

If the answer is NO, then:
1. Make the changes
2. Test the changes
3. Show what was done
4. **STOP and WAIT for "commit" instruction**

Only proceed with `git commit` if you have explicit permission.
