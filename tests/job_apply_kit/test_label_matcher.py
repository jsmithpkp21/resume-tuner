"""Unit tests for `job_apply_kit.label_matcher`.

Covers:
- normalize(): trailing-punct stripping, whitespace collapsing, embedded newlines
- is_honeypot(): substring detection against the canonical patterns
- match(): canonical-synonym matching, sub-field heuristics, honeypot skip,
  empty-value skip when bank entry is blank, unresolved-sub-key when the
  resolver returns None (matcher gap), intentional-skip when the resolver
  returns "" (matcher declined to fill by design), no-match for unrecognized
  labels
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


class TestSubKeyResolversForMultiFieldSections:
    """The per-section resolvers MUST route to the right sub_key for
    multi-field sections like [preferences], [work_authorization], [eeo],
    [referral], [consent], [account]. The earlier "pick first key in TOML
    order" generic fallback could mis-route, e.g. "Travel requirements"
    landing on preferences.salary_expectation_usd just because it's first.
    """

    _MULTI_BANK: dict[str, object] = {
        "preferences": {
            "salary_expectation_usd": "150000",
            "earliest_start_date": "Two weeks",
            "willing_to_relocate": "no",
            "remote_preference": "remote",
            "notice_period_days": "14",
            "travel_pct_ok": "0-10%",
            "compensation_alignment": "yes",
            "synonyms": [
                "salary",
                "salary expectation",
                "start date",
                "notice period",
                "relocate",
                "remote",
                "travel",
                "travel requirements",
                "does the listed compensation align with your expectations",
            ],
        },
        "work_authorization": {
            "authorized_us": "yes",
            "sponsorship_needed": "no",
            "visa_status": "U.S. Citizen",
            "synonyms": [
                "authorized to work",
                "require sponsorship",
                "visa status",
            ],
        },
        "eeo": {
            "gender": "Decline",
            "race_ethnicity": "Decline",
            "veteran_status": "I am not a veteran",
            "disability_status": "No",
            "hispanic_or_latino": "no",
            "synonyms": [
                "gender",
                "race",
                "ethnicity",
                "hispanic",
                "latino",
                "veteran",
                "disability",
            ],
        },
        "referral": {
            "source": "LinkedIn",
            "referrer_name": "",
            "synonyms": ["how did you hear", "source", "referred by"],
        },
        "consent": {
            "job_alerts_marketing": False,
            "terms_of_use_agreed": True,
            "privacy_notice_acknowledged": True,
            "synonyms": [
                "yes, i agree to the terms of use and privacy policy",
                "yes, i would like to receive job alerts and marketing",
                "i acknowledge",
            ],
        },
        "account": {
            "password_lookup_path": "data/applications/credentials.toml",
            "synonyms": ["password*", "verify new password*"],
        },
    }

    def test_salary_routes_to_salary_expectation(self) -> None:
        d = match("Salary Expectation", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.section == "preferences"
        assert d.sub_key == "salary_expectation_usd"

    def test_travel_routes_to_travel_pct(self) -> None:
        # The bug Copilot caught: this used to land on salary_expectation_usd
        # because that was first in TOML order. Resolver must route to travel.
        d = match("Travel requirements", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "travel_pct_ok"

    def test_relocate_routes_correctly(self) -> None:
        d = match("Willing to relocate", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "willing_to_relocate"

    def test_remote_routes_correctly(self) -> None:
        d = match("Remote preference", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "remote_preference"

    def test_sponsorship_routes_correctly(self) -> None:
        d = match(
            "Will you now or in the future require sponsorship for employment visa status?",
            self._MULTI_BANK,
        )
        assert isinstance(d, Match)
        assert d.section == "work_authorization"
        assert d.sub_key == "sponsorship_needed"

    def test_authorized_routes_correctly(self) -> None:
        d = match("Are you authorized to work in the US?", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "authorized_us"

    def test_visa_status_routes_correctly(self) -> None:
        d = match("Visa Status", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "visa_status"

    def test_gender_routes_correctly(self) -> None:
        d = match("Gender", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.section == "eeo"
        assert d.sub_key == "gender"

    def test_veteran_routes_correctly(self) -> None:
        d = match("Veteran Status", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "veteran_status"

    def test_disability_routes_correctly(self) -> None:
        d = match("Disability Status", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "disability_status"

    def test_referral_source(self) -> None:
        d = match("How did you hear about us?", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.section == "referral"
        assert d.sub_key == "source"

    def test_terms_consent_routes_correctly_with_bool_value(self) -> None:
        # [consent] uses booleans — exercises the bool/int fallback fix
        d = match(
            "Yes, I agree to the Terms of Use and Privacy Policy*",
            self._MULTI_BANK,
        )
        assert isinstance(d, Match)
        assert d.section == "consent"
        assert d.sub_key == "terms_of_use_agreed"
        assert d.value == "True"  # bool stringified for display

    def test_marketing_routes_to_job_alerts(self) -> None:
        d = match(
            "Yes, I would like to receive job alerts and marketing",
            self._MULTI_BANK,
        )
        assert isinstance(d, Match)
        assert d.sub_key == "job_alerts_marketing"

    def test_password_routes_to_lookup_path(self) -> None:
        # password resolver must return password_lookup_path (the answer-bank
        # pointer to credentials.toml), not the now-removed password_hint key
        d = match("Password*", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.section == "account"
        assert d.sub_key == "password_lookup_path"

    def test_verify_password_also_routes_to_lookup_path(self) -> None:
        d = match("Verify New Password*", self._MULTI_BANK)
        assert isinstance(d, Match)
        assert d.sub_key == "password_lookup_path"


class TestGenericFallbackFailsClosedWhenAmbiguous:
    """If a multi-field section has no registered resolver, the generic
    fallback must fail-closed rather than confidently picking the first
    TOML key. (Caught by PR #350 review round 2.)"""

    def test_multi_field_section_without_resolver_skips(self) -> None:
        # An unknown section with two fillable keys + a matching synonym
        bank = {
            "custom_section": {
                "first_value": "A",
                "second_value": "B",
                "synonyms": ["custom field"],
            },
        }
        d = match("Custom field", bank)
        assert isinstance(d, Skip)
        assert d.reason == "unresolved-sub-key"
        assert "no resolver" in d.detail

    def test_single_field_unknown_section_works(self) -> None:
        # Single fillable key → safe to auto-pick
        bank = {
            "thing": {
                "only_key": "value",
                "synonyms": ["the thing"],
            },
        }
        d = match("The thing", bank)
        assert isinstance(d, Match)
        assert d.sub_key == "only_key"


class TestUnresolvedSubKey:
    """Skip(reason="unresolved-sub-key") covers two matcher-internal cases:
    (a) registered resolver returned "" for this label (heuristic miss),
    (b) multi-field section has no registered resolver (fail-closed).
    Case (b) is covered by TestGenericFallbackFailsClosedWhenAmbiguous above;
    this class adds the missing (a) coverage (PR #354 review).
    """

    def test_resolver_returns_empty_sub_key_triggers_unresolved(self) -> None:
        # profile_fields' resolver only recognizes headline / pronoun /
        # summary substrings — a "bio" label routes INTO the section
        # (synonym match) but the resolver returns "". That's a matcher
        # gap (extend _sub_key_for_profile_fields), not a bank-blank case.
        bank = {
            "profile_fields": {
                "headline": "Staff SDET",
                "preferred_pronouns": "they/them",
                "summary": "Long bio summary",
                "synonyms": ["bio"],
            },
        }
        d = match("Bio", bank)
        assert isinstance(d, Skip)
        assert d.reason == "unresolved-sub-key"
        assert "no fillable sub-key" in d.detail

    def test_section_with_no_fillable_keys_is_empty_value(self) -> None:
        # candidates == 0 in the generic fallback: every non-`synonyms`
        # key is None or blank-string. That's a bank-empty case (operator
        # should fill the bank), distinct from a matcher gap.
        bank = {
            "empty_section": {
                "k1": None,
                "k2": "",
                "synonyms": ["empty field"],
            },
        }
        d = match("Empty field", bank)
        assert isinstance(d, Skip)
        assert d.reason == "empty-value"
        assert "no fillable keys" in d.detail


class TestIntentionalSkip:
    """Resolvers return "" (not None) for labels they recognize but
    deliberately decline to fill. Replay summaries should surface these
    as `intentional-skip` so the operator doesn't waste time "extending
    the matcher" — the matcher is working as designed. (Added in #355.)
    """

    def test_phone_extension_is_intentional_skip(self) -> None:
        # Workday's phone-extension field — _sub_key_for_contact returns
        # "" because we don't fill extensions even though we know what
        # the label means.
        bank = {
            "contact": {
                "email": "jane@example.com",
                "phone_pretty": "+1 555 0123",
                "synonyms": ["phone extension", "extension"],
            },
        }
        d = match("Phone Extension", bank)
        assert isinstance(d, Skip)
        assert d.reason == "intentional-skip"
        assert "contact" in d.detail

    def test_facebook_link_is_intentional_skip(self) -> None:
        # _sub_key_for_links returns "" for facebook/twitter — we don't
        # track those social links by design.
        bank = {
            "links": {
                "linkedin_url": "https://linkedin.com/in/jane",
                "website_url": "https://example.com",
                "synonyms": ["facebook", "facebook profile"],
            },
        }
        d = match("Facebook Profile", bank)
        assert isinstance(d, Skip)
        assert d.reason == "intentional-skip"

    def test_remember_me_is_intentional_skip(self) -> None:
        # _sub_key_for_account returns "" for "remember me" — it's a
        # boolean checkbox the caller handles separately, not a fillable
        # text value the matcher should resolve.
        bank = {
            "account": {
                "password_lookup_path": "credentials.toml#some_ats",
                "synonyms": ["remember me"],
            },
        }
        d = match("Remember me", bank)
        assert isinstance(d, Skip)
        assert d.reason == "intentional-skip"


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
