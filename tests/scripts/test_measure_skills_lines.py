"""Tests for spike #43: skills line measurement loop.

Validates the three acceptance criteria from Issue #43:
  1. Repeated measurement of same inputs is deterministic.
  2. Adding/removing one skill can shift line count by exactly ±1.
  3. The report structure is well-formed for downstream use by #42.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.measure_skills_lines import (
    TARGET_LINES_MAX,
    KernTable,
    load_font_pair,
    load_kern_table,
    load_skills_by_category,
    measure_skills_section,
    wrap_category_line,
)

# ---------------------------------------------------------------------------
# Module-level setup helpers (cached after first call — fonts are read-only)
# Project pattern: no @pytest.fixture decorators (none used elsewhere in suite).
# ---------------------------------------------------------------------------

SKILLS_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "skills"
    / "skills_matrix.csv"
)

_fonts_cache: tuple[Any, Any, str] | None = None
_skills_cache: dict[str, list[str]] | None = None
_kern_cache: KernTable | None = None
_kern_loaded: bool = False


def _get_fonts() -> tuple[Any, Any, str]:
    """Load font pair once for the whole module."""
    global _fonts_cache
    if _fonts_cache is None:
        _fonts_cache = load_font_pair()
    return _fonts_cache


def _get_skills() -> dict[str, list[str]]:
    """Load skills by category from CSV file."""
    global _skills_cache
    if _skills_cache is None:
        _skills_cache = load_skills_by_category(SKILLS_CSV)
    return _skills_cache


def _get_kern() -> KernTable | None:
    """Load kern table once for the whole class (None if Calibri unavailable)."""
    global _kern_cache, _kern_loaded
    if not _kern_loaded:
        _kern_cache = load_kern_table()
        _kern_loaded = True
    return _kern_cache


# ---------------------------------------------------------------------------
# Acceptance criterion 1: determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """AC-1: same inputs → same output every time."""

    def test_wrap_count_is_deterministic(self) -> None:
        font_regular, font_bold, _ = _get_fonts()
        skills = ["Python", "Java", "Bash", "Groovy", "Shell scripting"]

        count_a, triggers_a = wrap_category_line(
            "Programming & Scripting",
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )
        count_b, triggers_b = wrap_category_line(
            "Programming & Scripting",
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )

        assert count_a == count_b
        assert triggers_a == triggers_b

    def test_full_report_is_deterministic(self) -> None:
        font_regular, font_bold, font_name = _get_fonts()
        report_a = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )
        report_b = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )

        assert report_a["summary"]["total_lines"] == report_b["summary"]["total_lines"]
        assert json.dumps(report_a, sort_keys=True) == json.dumps(
            report_b, sort_keys=True
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 2: ±1 line sensitivity
# ---------------------------------------------------------------------------


class TestLineSensitivity:
    """AC-2: adding or removing one skill can shift the line count by ±1."""

    def test_adding_one_skill_can_increase_line_count(self) -> None:
        """Adding a skill to a line already near the wrap point adds a line."""
        font_regular, font_bold, _ = _get_fonts()

        base_skills = [
            "Python",
            "Java",
            "Bash",
            "Groovy",
            "C",
            "C++",
            "JavaScript",
            "TypeScript",
            "Shell scripting",
        ]
        extended_skills = base_skills + ["PowerShell scripting"]

        count_before, _ = wrap_category_line(
            "Programming & Scripting",
            base_skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )
        count_after, _ = wrap_category_line(
            "Programming & Scripting",
            extended_skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )

        assert count_after == count_before + 1, (
            f"Expected +1 line after adding a skill: before={count_before} after={count_after}"
        )

    def test_removing_skill_can_decrease_line_count(self) -> None:
        """Removing a wide skill that causes wrapping collapses the line count."""
        font_regular, font_bold, _ = _get_fonts()

        # "W" is the widest glyph in Calibri; 55 chars guarantees overflow at 11pt.
        wide_skill = "W" * 55
        skills_wrapping = [
            "Python",
            "Java",
            "Bash",
            "Groovy",
            "Shell scripting",
            wide_skill,
        ]
        skills_trimmed = [s for s in skills_wrapping if s != wide_skill]

        count_with, _ = wrap_category_line(
            "Category",
            skills_wrapping,
            font_regular=font_regular,
            font_bold=font_bold,
        )
        if count_with == 1:
            pytest.skip(
                "Wide skill still fits on one line with this font; "
                "increase wide_skill length if Calibri metrics change."
            )
            return
        count_without, _ = wrap_category_line(
            "Category",
            skills_trimmed,
            font_regular=font_regular,
            font_bold=font_bold,
        )

        assert count_without < count_with, (
            f"Expected fewer lines after removing a wide skill: "
            f"with={count_with} without={count_without}"
        )

    def test_single_skill_rename_can_change_line_count(self) -> None:
        """Shortening one skill name that was the wrap trigger removes the wrap."""
        font_regular, font_bold, _ = _get_fonts()

        skills_long = [
            "Distributed systems",
            "Distributed tracing",
            "Hybrid cloud interactions (on-prem <-> cloud)",
            "Multi-device automation labs",
            "VM-based testbeds",
        ]
        skills_short = [
            "Distributed systems",
            "Distributed tracing",
            "Hybrid cloud interactions",
            "Multi-device automation labs",
            "VM-based testbeds",
        ]

        count_long, _ = wrap_category_line(
            "Distributed Systems & Infrastructure",
            skills_long,
            font_regular=font_regular,
            font_bold=font_bold,
        )
        count_short, _ = wrap_category_line(
            "Distributed Systems & Infrastructure",
            skills_short,
            font_regular=font_regular,
            font_bold=font_bold,
        )

        assert count_short <= count_long, (
            "Shortening a skill name should not increase line count"
        )


# ---------------------------------------------------------------------------
# Acceptance criterion 3: report structure
# ---------------------------------------------------------------------------


class TestReportStructure:
    """AC-3: the report is well-formed and usable by issue #42."""

    def test_report_has_required_keys(self) -> None:
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )

        assert "reference_layout" in report
        assert "summary" in report
        assert "categories" in report

        layout = report["reference_layout"]
        assert "text_width_pt" in layout
        assert "text_width_in" in layout
        assert "font" in layout
        assert "kerning_enabled" in layout
        assert "kern_pairs" in layout

        summary = report["summary"]
        assert "total_lines" in summary
        assert "category_count" in summary
        assert "within_budget" in summary
        assert isinstance(summary["total_lines"], int)
        assert summary["total_lines"] > 0

    def test_each_category_entry_has_required_keys(self) -> None:
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )

        for cat in report["categories"]:
            assert "category" in cat
            assert "skill_count" in cat
            assert "line_count" in cat
            assert "wrap_trigger_words" in cat
            assert "full_line_width_pt" in cat
            assert "unwrapped_overflow_pt" in cat
            assert isinstance(cat["line_count"], int)
            assert cat["line_count"] >= 1

    def test_total_lines_equals_sum_of_category_lines(self) -> None:
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )
        expected_total = sum(cat["line_count"] for cat in report["categories"])
        assert report["summary"]["total_lines"] == expected_total

    def test_single_short_line_does_not_wrap(self) -> None:
        """A known-short category should always produce exactly 1 line."""
        font_regular, font_bold, _ = _get_fonts()
        count, triggers = wrap_category_line(
            "Networking",
            ["TCP/IP fundamentals"],
            font_regular=font_regular,
            font_bold=font_bold,
        )
        assert count == 1
        assert triggers == []

    def test_full_skills_section_is_over_budget(self) -> None:
        """Full unfiltered skills matrix should be well over the 10-13 line budget,
        confirming that category selection / trimming is required."""
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )
        assert report["summary"]["total_lines"] > TARGET_LINES_MAX, (
            "Full skills matrix should require trimming to fit within budget"
        )

    def test_report_is_json_serialisable(self) -> None:
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            _get_skills(),
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
        )
        serialised = json.dumps(report)
        roundtripped = json.loads(serialised)
        assert (
            roundtripped["summary"]["total_lines"] == report["summary"]["total_lines"]
        )


# ---------------------------------------------------------------------------
# Kerning tests (fontTools kern table)
# ---------------------------------------------------------------------------


class TestKerning:
    """Tests for the optional fontTools-based kerning layer."""

    def test_kern_table_loads_when_calibri_present(self) -> None:
        """KernTable should load when Calibri is installed."""
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed; kern table unavailable")
            return
        assert kern.pair_count > 0, "Expected at least one kern pair in Calibri"

    def test_calibri_kern_has_expected_pair_count(self) -> None:
        """Calibri has 2,000+ Unicode-mapped kern pairs (glyphs without codepoints excluded).

        Note: the raw kern table has 26,706 entries, but ~24,000 are for composite
        glyphs without Unicode codepoints.  Our KernTable only stores character pairs
        where both glyphs map to Unicode — the meaningful set for text measurement.
        """
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed")
            return
        assert kern.pair_count >= 2_000, (
            f"Expected ≥2,000 Unicode-mapped kern pairs; got {kern.pair_count}. "
            "Possibly loading wrong font or partial kern table."
        )

    def test_av_kern_pair_is_negative(self) -> None:
        """A-V is a well-known tight-kerned pair; adjustment must be negative."""
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed")
            return
        adj = kern.adjust_pt("A", "V")
        assert adj < 0, f"kern(A,V) should be negative (got {adj:.3f}pt)"

    def test_to_kern_pair_is_significantly_negative(self) -> None:
        """T-o has one of the largest kern adjustments in Latin fonts."""
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed")
            return
        adj = kern.adjust_pt("T", "o")
        assert adj < -0.5, f"kern(T,o) should be < −0.5 pt at 11pt (got {adj:.3f}pt)"

    def test_kern_reduces_or_equals_no_kern_line_width(self) -> None:
        """Line width with kerning must be ≤ width without kerning (kern is tightening)."""
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed")
            return
        font_regular, font_bold, _ = _get_fonts()
        skills = [
            "Automation",
            "Testing",
            "TypeScript",
            "Python",
            "CI/CD frameworks",
        ]
        count_no_kern, _ = wrap_category_line(
            "Automation & Testing",
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
            kern_table=None,
        )
        count_with_kern, _ = wrap_category_line(
            "Automation & Testing",
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
            kern_table=kern,
        )
        # Kerning can only reduce (tighten) or maintain line count — never increase it.
        assert count_with_kern <= count_no_kern, (
            f"Kerning increased line count: {count_no_kern} → {count_with_kern}"
        )

    def test_report_records_kern_metadata(self) -> None:
        """Report reference_layout must record kerning_enabled and kern_pairs."""
        kern = _get_kern()
        if kern is None:
            pytest.skip("Calibri not installed")
            return
        font_regular, font_bold, font_name = _get_fonts()
        report = measure_skills_section(
            {"Programming & Scripting": ["Python", "Bash"]},
            font_regular=font_regular,
            font_bold=font_bold,
            font_name=font_name,
            kern_table=kern,
        )
        layout = report["reference_layout"]
        assert layout["kerning_enabled"] is True
        assert layout["kern_pairs"] == kern.pair_count


class TestRuntimeGuards:
    """Ensure runtime path guard blocks unsafe CLI input paths."""

    def test_load_skills_rejects_blocked_csv_path(self) -> None:
        blocked_csv = Path("sandbox") / "skills_matrix.csv"
        with pytest.raises(ValueError, match="blocked runtime directory"):
            load_skills_by_category(blocked_csv)
