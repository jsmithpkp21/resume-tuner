"""Unit tests for scripts/document_export.py.

Covers the slug-length cap added in #280 and the existing happy paths
of `snake_case` / `canonical_export_filename` so future refactors don't
silently regress filename safety.
"""

from __future__ import annotations

import pytest

from scripts.document_export import (
    MAX_COMPANY_SLUG_CHARS,
    canonical_export_filename,
    snake_case,
)

# --- snake_case: basic shape -------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Acme Corp", "acme_corp"),
        ("HP / Poly", "hp_poly"),
        ("  spaces  ", "spaces"),
        ("Already_snake_cased", "already_snake_cased"),
        ("", "company"),  # empty input → fallback
        ("   ", "company"),  # whitespace-only → fallback
        ("---", "company"),  # punctuation-only → fallback
    ],
)
def test_snake_case_basic_shape(raw: str, expected: str) -> None:
    assert snake_case(raw) == expected


# --- snake_case: #280 length cap --------------------------------------------


def test_snake_case_caps_at_max_company_slug_chars() -> None:
    """Long input must not exceed MAX_COMPANY_SLUG_CHARS.

    Issue #280: pre-fix the LLM company-extraction fallback emitted a
    250+ char slug from JD prose, breaking `.docx` export with
    `[Errno 36] File name too long`. Cap is enforced here so every
    downstream path (canonical_export_filename, staging_path, etc.)
    inherits the bound.
    """
    raw = (
        "RadarFirst Build What Matters in Regulatory Risk and AI Governance "
        "Join a Team Helping Organizations Make Confident Defensible Decisions "
        "in a World of Increasing Regulatory Complexity"
    )
    out = snake_case(raw)
    assert len(out) <= MAX_COMPANY_SLUG_CHARS
    # The cap retains the legitimate company name prefix (truncates at a
    # word boundary, not mid-word).
    assert out.startswith("radarfirst")
    assert not out.endswith("_")


def test_snake_case_truncates_at_last_underscore_boundary() -> None:
    """Cap should land on a word boundary, not split a token mid-word.

    Input is constructed so the snake_case'd form exceeds the 64-char cap
    AND has the cap fall mid-token; the function must back up to the
    nearest underscore so the trailing token is a complete word from
    the input rather than a mid-word fragment.
    """
    raw = "company1 with a very extensive marketing tagline that goes on and on and on"
    out = snake_case(raw)
    assert len(out) <= MAX_COMPANY_SLUG_CHARS
    assert not out.endswith("_")
    # The trailing token must be a complete word from the input — never
    # a mid-word fragment like "an" (a partial cut of "and").
    legitimate_words = {
        "company1",
        "with",
        "a",
        "very",
        "extensive",
        "marketing",
        "tagline",
        "that",
        "goes",
        "on",
        "and",
    }
    last = out.rsplit("_", 1)[-1]
    assert last in legitimate_words, f"trailing token {last!r} is mid-word; out={out!r}"


def test_snake_case_hard_cuts_when_no_underscore_under_cap() -> None:
    """If the input has no `_` boundary inside the cap, take a hard cut.

    This is the degenerate case of a single very long token — uncommon in
    practice but the function must still return ≤ cap chars and never an
    empty string for a non-empty input.
    """
    raw = "x" * (MAX_COMPANY_SLUG_CHARS * 3)
    out = snake_case(raw)
    assert len(out) == MAX_COMPANY_SLUG_CHARS
    assert out == "x" * MAX_COMPANY_SLUG_CHARS


def test_snake_case_passes_through_short_input_unchanged() -> None:
    """Short inputs (the common case) are not modified by the cap path."""
    out = snake_case("Murmuration")
    assert out == "murmuration"
    assert len(out) <= MAX_COMPANY_SLUG_CHARS


# --- canonical_export_filename: cap propagates ------------------------------


def test_canonical_export_filename_inherits_slug_cap() -> None:
    """The cap on `snake_case` flows through `canonical_export_filename`.

    Confirms the bug-fix surface: filename produced for a JD-derived
    company name fits under typical filesystem NAME_MAX (255) even when
    the company input is hundreds of chars.
    """
    big_company = "x " * 200  # ~400 chars input
    name = canonical_export_filename(big_company, "docx")
    # snake_case cap (64) + "_resume.docx" (12) = 76 chars max.
    assert len(name) <= MAX_COMPANY_SLUG_CHARS + len("_resume.docx")
    assert name.endswith("_resume.docx")
