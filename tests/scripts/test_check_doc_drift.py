"""Tests for `scripts/check_doc_drift.py`.

The check is regex+filesystem based, so the test strategy points the
script at a temporary tree we control rather than the real `src/`.
We load the script's `_DENY_PATTERNS` to exercise the matching logic
parametrically, plus invoke the script as a subprocess to verify the
exit code + stderr formatting end-to-end.

The script is loaded via `importlib.util.spec_from_file_location` so
the test doesn't mutate `sys.path` (which would persist across the
whole pytest run and risk colliding with any other top-level modules
named `check_doc_drift`).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

# Load the script as a one-off module without touching sys.path. The
# script keeps its REPO_ROOT relative to its own `__file__`, so this
# import only exercises the patterns; the end-to-end tests below copy
# the script into a tmp tree to retarget REPO_ROOT for each test.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_doc_drift.py"
_spec = importlib.util.spec_from_file_location("check_doc_drift", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_doc_drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_doc_drift)


def _run_check(repo_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the script with `repo_root` swapped in via REPO_ROOT env."""
    # The script computes REPO_ROOT from `__file__`. Easiest way to
    # point it at a temp tree is to copy the script into the temp
    # tree's `scripts/` dir and run it from there — its
    # `parents[1]` resolution then lands on the temp root.
    temp_script = repo_root / "scripts" / "check_doc_drift.py"
    src = _REPO_ROOT / "scripts" / "check_doc_drift.py"
    temp_script.parent.mkdir(parents=True, exist_ok=True)
    temp_script.write_text(src.read_text(), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(temp_script)],
        capture_output=True,
        text=True,
        check=False,
    )


class TestDenyListPatterns:
    """The patterns themselves — verify the regex matches the literal
    phrases we care about and not similar non-matching strings."""

    @pytest.mark.parametrize(
        "line",
        [
            "page.fill('foo')",
            "calls page.fill() at startup",
            "use page.click(button)",
            "page.select_option(value='x')",
            "page.check() toggles the box",
        ],
    )
    def test_known_drift_phrases_match(self, line: str) -> None:
        matched = any(pat.search(line) for pat, _ in check_doc_drift._DENY_PATTERNS)
        assert matched, f"expected drift phrase to match in: {line!r}"

    @pytest.mark.parametrize(
        "line",
        [
            "Locator.fill('foo')",  # the new correct API
            "self.page = something",  # `page.` followed by non-method
            "homepage.fill_in_form()",  # word boundary protects this
            "no API mentioned here at all",
        ],
    )
    def test_non_drift_phrases_do_not_match(self, line: str) -> None:
        matched = any(pat.search(line) for pat, _ in check_doc_drift._DENY_PATTERNS)
        assert not matched, f"expected NO match in: {line!r}"


class TestEndToEnd:
    """Full subprocess invocation against a synthetic temp tree."""

    def test_clean_tree_exits_zero(self, tmp_path: Path) -> None:
        # Empty src/ — nothing to scan, exit 0.
        (tmp_path / "src").mkdir()
        result = _run_check(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_hit_exits_nonzero_with_diagnostic(self, tmp_path: Path) -> None:
        # Plant a Python file with a drift phrase.
        src = tmp_path / "src" / "myapp.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            '"""Module that calls page.fill internally."""\n',
            encoding="utf-8",
        )
        result = _run_check(tmp_path)
        assert result.returncode == 1
        assert "page.fill" in result.stderr
        assert "src/myapp.py:1" in result.stderr

    def test_opt_out_marker_skips_the_line(self, tmp_path: Path) -> None:
        # Same drift phrase, but with the opt-out marker → exit 0.
        src = tmp_path / "src" / "historical.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            '"""Historical API — page.fill was used here.  # noqa: doc-drift"""\n',
            encoding="utf-8",
        )
        result = _run_check(tmp_path)
        assert result.returncode == 0, result.stderr

    def test_scans_js_too(self, tmp_path: Path) -> None:
        # Drift in a JS file should also be caught (relevant for
        # field_extractor.js etc.).
        js = tmp_path / "scripts" / "extractor.js"
        js.parent.mkdir(parents=True)
        js.write_text("// uses page.click() internally\n", encoding="utf-8")
        result = _run_check(tmp_path)
        assert result.returncode == 1
        assert "page.click" in result.stderr

    def test_skips_self_to_avoid_meta_match(self, tmp_path: Path) -> None:
        # `check_doc_drift.py` itself contains the deny-list strings.
        # The script intentionally skips its own basename so it
        # doesn't flag the patterns in its own source. (This is the
        # behavior we get from copying the real script into the temp
        # tree above — verify it stays out of the output.)
        result = _run_check(tmp_path)
        assert "check_doc_drift.py" not in result.stderr
