#!/usr/bin/env python3
"""Shared measurable-outcome detection helpers used across resume scripts."""

from __future__ import annotations

import re

MEASURABLE_OUTCOME_PERCENT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent|x)\b", re.IGNORECASE
)
MEASURABLE_OUTCOME_VERB_PATTERN = re.compile(
    r"\b(?:"
    r"reduc(?:e|ed|es|ing)|"
    r"improv(?:e|ed|es|ing)|"
    r"increas(?:e|ed|es|ing)|"
    r"decreas(?:e|ed|es|ing)|"
    r"cut(?:s|ting)?|"
    r"sav(?:e|ed|es|ing)|"
    r"boost(?:e|ed|es|ing)|"
    r"eliminat(?:e|ed|es|ing)|"
    r"mentor(?:s|ed|ing)?|"
    r"doubl(?:e|ed|es|ing)|"
    r"tripl(?:e|ed|es|ing)|"
    r"accelerat(?:e|ed|es|ing)|"
    r"scal(?:e|ed|es|ing)|"
    r"grow(?:s|ing|n)?|grew"
    r")\b",
    re.IGNORECASE,
)
MEASURABLE_OUTCOME_NUMBER_WORD_PATTERN = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred)\b",
    re.IGNORECASE,
)


def has_measurable_outcome(text: str) -> bool:
    """Return True when text contains quantified outcome language."""
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return False
    if MEASURABLE_OUTCOME_PERCENT_PATTERN.search(normalized):
        return True
    return bool(
        MEASURABLE_OUTCOME_VERB_PATTERN.search(normalized)
        and (
            re.search(r"\b\d+(?:\.\d+)?\b", normalized)
            or MEASURABLE_OUTCOME_NUMBER_WORD_PATTERN.search(normalized)
        )
    )
