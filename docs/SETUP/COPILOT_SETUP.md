# Copilot Agent Mode - IDE Setup

This document explains how Copilot works in agent mode within PyCharm IDE for this project.

## Overview

Copilot runs in agent mode inside PyCharm and automatically uses the `.github/copilot-instructions.md` file to generate code that matches project standards.

## How It Works

**PyCharm automatically discovers and loads** `.github/copilot-instructions.md` when:
1. You open the project in PyCharm
2. You use Copilot to generate or edit code
3. Copilot uses the instructions to generate standards-compliant code

**No setup required** - it works automatically!

## What Copilot Will Generate

When you ask Copilot to generate code, it will automatically include:

✅ Type hints on all functions and variables
✅ Google-style docstrings
✅ Code formatted to 88 characters per line
✅ Proper import organization (stdlib, third-party, local)
✅ Specific exception handling (no bare `except:`)
✅ Clear, actionable error messages
✅ Tests alongside code
✅ Proper naming conventions (snake_case, PascalCase)

## Instructions Coverage

The instructions in `.github/copilot-instructions.md` cover:

- ✅ Type hints (MANDATORY)
- ✅ Docstrings (Google-style, MANDATORY)
- ✅ Code style (PEP 8 + Black, 88 chars)
- ✅ Naming conventions (snake_case, PascalCase, SCREAMING_SNAKE_CASE)
- ✅ Linting standards (Ruff, Black, Isort, Mypy)
- ✅ File naming conventions
- ✅ Code organization patterns
- ✅ Error handling best practices
- ✅ Testing requirements
- ✅ Common code generation patterns
- ✅ Pre-commit checklist

## Verification

To verify Copilot is using the instructions:

1. Generate a function with Copilot
2. Check that it includes:
   - ✅ Type hints on all parameters and return types
   - ✅ Google-style docstring
   - ✅ Lines under 88 characters
   - ✅ Proper import organization
   - ✅ Error handling with specific exceptions

If code doesn't follow standards:
1. Close and reopen PyCharm
2. Or use `File` → `Invalidate Caches` → `Invalidate and Restart`

## Using Copilot

### Example: Generate a Function

**You ask:** "Create a function to validate a config file"

**Copilot generates (with standards applied automatically):**
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
            f"Configuration file not found: {config_path}"
        )

    with open(config_path) as f:
        config: dict[str, str] = tomllib.load(f)

    return config
```

### Example: Generate Tests

**You ask:** "Generate tests for validate_config"

**Copilot generates (with standards applied automatically):**
```python
def test_validate_config_success(self) -> None:
    """Test successful config validation."""
    config_path: str = "test_config.toml"
    expected: dict[str, str] = {"key": "value"}

    result: dict[str, str] = validate_config(config_path)

    assert result == expected

def test_validate_config_missing_file(self) -> None:
    """Test error when config file missing."""
    with pytest.raises(FileNotFoundError):
        validate_config("nonexistent.toml")
```

## No Manual Fixes Needed

Because Copilot uses these instructions automatically:
- ✅ Code passes `make lint` immediately
- ✅ Code passes `make test` immediately
- ✅ No "add type hints" code review comments
- ✅ No "fix linting" iterations
- ✅ No "add docstrings" requests

## Project Standards

All Copilot-generated code in this project will:
- Follow the project's coding standards
- Be production-ready
- Pass all linting checks
- Include comprehensive tests
- Have proper error handling

## Questions?

Refer to:
- `COPILOT_QUICK_REFERENCE.md` - Quick examples of what Copilot generates
- `.github/copilot-instructions.md` - Full detailed standards
- `MANIFESTO.md` - Design philosophy behind the standards
