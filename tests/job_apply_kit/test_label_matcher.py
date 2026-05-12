"""Unit tests for `job_apply_kit.label_matcher`.

Covers:
- normalize(): trailing-punct stripping, whitespace collapsing, embedded newlines
- is_honeypot(): substring detection against the canonical patterns
- match(): canonical-synonym matching, sub-field heuristics, honeypot skip,
  empty-value skip when bank entry is blank, no-match for unrecognized labels
- Decision typing (Match vs Skip)

The matcher is pure — no I/O, no Playwright, no captures — so these tests
run unconditionally in any environment.
"""

from __future__ import annotations

import pytest

from job_apply_kit import (
    HONEYPOT_SUBSTRINGS,
    Match,
    Skip,
    is_honeypot,
    match,
    normalize,
)

# A representative answer bank with TODO blanks + filled values to exercise
# both the matched-and-fillable and matched-but-empty paths.
_BANK: dict[str, object] = {
    "name": {
        "first": "Jane",
        "middle": "Q",
        "last": "Doe",
        "preferred": "Janey",
        "synonyms": [
            "first name",
            "first name*",
            "last name",
            "last name*",
            "middle name",
            "preferred name",
            "name*",
        ],
    },
    "contact": {
        "email": "jane@example.com",
        "phone_pretty": "555-123-4567",
        "country_phone_code": "+1",
        "synonyms": [
            "email",
            "email address",
            "email address*",
            "phone",
            "phone number*",
            "country phone code",
            "telephone country code",
        ],
    },
    "address": {
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
        "country": "United States",
        "street1": "",  # blank TODO
        "synonyms": [
            "address",
            "city",
            "city*",
            "state",
            "zip",
            "postal code",
            "postal code*",
            "country",
            "address line 1*",
        ],
    },
    "links": {
        "linkedin_url": "https://www.linkedin.com/in/jane-doe",
        "github_url": "",
        "website_url": "",
        "synonyms": ["linkedin", "linkedin url", "linkedin profile", "github"],
    },
    "work_authorization": {
        "authorized_us": "",  # TODO blank
        "synonyms": [
            "authorized to work",
            "will you now or in the future require sponsorship for employment visa status",
        ],
    },
    "age_check": {
        "answer": "Yes",
        "synonyms": ["are you 18 years of age or older"],
    },
    "honeypot": {
        # Section is intentionally excluded from matching — see _NON_FILL_SECTIONS.
        "fields_to_skip": [
            "Enter website. This input is for robots only, do not enter if you're human.",
        ],
    },
    "work_experience": {
        # Also excluded from matching — structural fields, not single values.
        "synonyms": ["job title*", "company*", "role description"],
    },
    "custom": {
        # Per-company essay answers; also excluded from auto-matching.
        "acme": {"why_this_company": "..."},
    },
}


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_strips_trailing_required_marker(self) -> None:
        assert normalize("First Name*") == "first name"

    def test_strips_trailing_question_mark(self) -> None:
        assert normalize("Are you 18 years of age or older?") == (
            "are you 18 years of age or older"
        )

    def test_collapses_internal_whitespace(self) -> None:
        # Workable produced labels with embedded newlines (e.g. "*\nPhone\n+1")
        assert normalize("Phone\n  Number") == "phone number"

    def test_strips_combined_trailing_punct(self) -> None:
        # `* ? : . !` plus whitespace, iteratively stripped until stable
        assert normalize("Name** !  ") == "name"

    def test_handles_empty_string(self) -> None:
        assert normalize("") == ""

    def test_lowercases(self) -> None:
        assert normalize("LinkedIn URL") == "linkedin url"


# ---------------------------------------------------------------------------
# is_honeypot()
# ---------------------------------------------------------------------------


class TestIsHoneypot:
    @pytest.mark.parametrize("phrase", HONEYPOT_SUBSTRINGS)
    def test_canonical_substrings_match(self, phrase: str) -> None:
        # Each canonical substring should trip the detector on its own
        assert is_honeypot(phrase)

    def test_full_workday_phrase_detected(self) -> None:
        # The actual label observed on BECU's + Western Union's Workday tenants
        assert is_honeypot(
            "Enter website. This input is for robots only, do not enter if you're human."
        )

    def test_innocuous_label_not_flagged(self) -> None:
        assert not is_honeypot("First Name*")
        assert not is_honeypot("Job Title*")


# ---------------------------------------------------------------------------
# match() — happy paths
# ---------------------------------------------------------------------------


class TestMatchHappyPath:
    def test_first_name(self) -> None:
        d = match("First Name*", _BANK)
        assert isinstance(d, Match)
        assert d.section == "name"
        assert d.sub_key == "first"
        assert d.value == "Jane"

    def test_last_name(self) -> None:
        d = match("Last name", _BANK)
        assert isinstance(d, Match)
        assert d.section == "name"
        assert d.sub_key == "last"
        assert d.value == "Doe"

    def test_preferred_name(self) -> None:
        d = match("Preferred name", _BANK)
        assert isinstance(d, Match)
        assert d.section == "name"
        assert d.sub_key == "preferred"

    def test_email(self) -> None:
        d = match("Email Address*", _BANK)
        assert isinstance(d, Match)
        assert d.section == "contact"
        assert d.sub_key == "email"
        assert d.value == "jane@example.com"

    def test_phone(self) -> None:
        d = match("Phone Number*", _BANK)
        assert isinstance(d, Match)
        assert d.section == "contact"
        assert d.sub_key == "phone_pretty"

    def test_country_phone_code(self) -> None:
        # Critical distinction: "Country Phone Code*" maps to country_phone_code,
        # NOT to phone_pretty or email — the sub-field resolver decides correctly.
        d = match("Country Phone Code*", _BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "country_phone_code"
        assert d.value == "+1"

    def test_country_as_address(self) -> None:
        # And bare "Country" (no "phone code" suffix) maps to address.country —
        # tests that the whole-word match doesn't false-positive against
        # "country phone code" synonym.
        d = match("Country", _BANK)
        assert isinstance(d, Match)
        assert d.section == "address"
        assert d.sub_key == "country"

    def test_linkedin_profile_via_substring_synonym(self) -> None:
        # "LinkedIn profile" matches synonym "linkedin" via whole-word containment
        d = match("LinkedIn profile", _BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "linkedin_url"

    def test_age_check_single_value_section(self) -> None:
        # [age_check] is in _SINGLE_VALUE_SECTIONS; sub_key is fixed to "answer"
        d = match("Are you 18 years of age or older?", _BANK)
        assert isinstance(d, Match)
        assert d.section == "age_check"
        assert d.sub_key == "answer"
        assert d.value == "Yes"


# ---------------------------------------------------------------------------
# match() — skip paths
# ---------------------------------------------------------------------------


class TestMatchSkipPaths:
    def test_honeypot_takes_priority(self) -> None:
        # Honeypot check runs before synonym matching
        d = match(
            "Enter website. This input is for robots only, do not enter if you're human.",
            _BANK,
        )
        assert isinstance(d, Skip)
        assert d.reason == "honeypot"

    def test_no_match_for_unrecognized_label(self) -> None:
        d = match("Some Field That Does Not Exist", _BANK)
        assert isinstance(d, Skip)
        assert d.reason == "no-match"

    def test_work_experience_labels_are_not_matched(self) -> None:
        # work_experience is in _NON_FILL_SECTIONS — structural fields the
        # fill driver's per-role loop must handle, not single-value fills.
        d = match("Job Title*", _BANK)
        assert isinstance(d, Skip)
        assert d.reason == "no-match"

    def test_empty_value_skip_when_bank_field_is_blank(self) -> None:
        # work_authorization synonym matches, but its values are all TODO blanks
        d = match(
            "Will you now or in the future require sponsorship for employment visa status?",
            _BANK,
        )
        assert isinstance(d, Skip)
        assert d.reason == "empty-value"
        assert "work_authorization" in d.detail

    def test_empty_label_skips(self) -> None:
        d = match("", _BANK)
        assert isinstance(d, Skip)
        assert d.reason == "no-match"


# ---------------------------------------------------------------------------
# Whole-word matching correctness regression
# ---------------------------------------------------------------------------


class TestWholeWordMatching:
    """The matcher uses regex `\\b...\\b` boundaries on synonym → label.

    Earlier (broken) bidirectional substring matching let "Country" falsely
    match the synonym "country phone code" via reverse substring. The fix
    requires the SHORT side be a whole-word substring of the LONG side, in
    the forward direction only.
    """

    def test_short_label_does_not_match_longer_synonym(self) -> None:
        # "Country" must NOT match "country phone code" via reverse substring.
        # If it did, the matcher would pick contact.country_phone_code; correct
        # answer is address.country.
        d = match("Country", _BANK)
        assert isinstance(d, Match)
        assert d.section == "address"

    def test_substring_match_requires_word_boundary(self) -> None:
        # Synonym "linkedin" appears in label "LinkedIn profile" as whole word
        d = match("LinkedIn profile", _BANK)
        assert isinstance(d, Match)
        assert d.section == "links"

    def test_partial_word_not_matched(self) -> None:
        # "gpa" should NOT match a label like "gpan" (no whole-word boundary)
        bank = {"education": {"gpa": "4.0", "synonyms": ["gpa"]}}
        d = match("gpan", bank)
        assert isinstance(d, Skip)
        assert d.reason == "no-match"
