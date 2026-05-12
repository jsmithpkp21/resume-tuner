"""Label-to-canonical-field matcher for the answer bank.

Pure functions. Given a form field's `label` string and the loaded
`_answer_bank.toml`, return what to fill (or skip, in the case of the
honeypot or an unrecognized label).

Phase 3 deliverable A: dry-run only — `fill_session.py` consumes these
decisions and logs them; no `page.fill()` calls land yet. See issue #319.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Honeypot substrings (case-insensitive). Source: PHASE_2_FINDINGS.md.
# Either match → skip the field. Both observed in Workday (BECU + WU).
HONEYPOT_SUBSTRINGS = (
    "input is for robots only",
    "do not enter if you're human",
)


@dataclass(frozen=True)
class Match:
    """The matcher's decision for a single field."""

    section: str  # canonical answer-bank section, e.g. "name"
    sub_key: str  # which value within the section, e.g. "first"
    value: str  # the actual value to fill
    matched_synonym: str  # which synonym in the bank caused the match (debug)


@dataclass(frozen=True)
class Skip:
    """Skip this field — explicit reason."""

    reason: str  # "honeypot" | "no-match" | "empty-value" | "unresolved-sub-key"
    detail: str = ""  # extra context for logs


Decision = Match | Skip


# -----------------------------
# Normalization
# -----------------------------

_WS_RE = re.compile(r"\s+")


def normalize(label: str) -> str:
    """Lowercase, strip whitespace + trailing required/punctuation marks,
    collapse internal whitespace.

    Workable produced labels with embedded newlines (e.g. `*\\nPhone\\n+1`);
    collapse those too. Trailing chars to strip: `* ? : . !` plus whitespace,
    so the captured "Will you now ... applies)?" matches the bank synonym
    "will you now ... applies)" without trailing punctuation churn.
    """
    if not label:
        return ""
    s = label.strip().lower()
    # Iteratively strip trailing punctuation + whitespace until stable.
    prev = ""
    while s != prev:
        prev = s
        s = s.rstrip("*?:.! \t\n")
    s = _WS_RE.sub(" ", s)
    return s


def is_honeypot(label: str) -> bool:
    """True if the label matches a known honeypot pattern (substring, case-insensitive)."""
    norm = normalize(label)
    return any(pat in norm for pat in HONEYPOT_SUBSTRINGS)


# -----------------------------
# Per-section sub-field heuristics
# -----------------------------
# Given a normalized label that matched a section's synonyms list, decide
# which sub-key within the section the value belongs to.


def _sub_key_for_name(norm: str) -> str:
    if "middle" in norm:
        return "middle"
    if "last" in norm or "family" in norm or "surname" in norm:
        return "last"
    if "preferred" in norm or "nickname" in norm or "name you go by" in norm:
        return "preferred"
    if "first" in norm or "given" in norm:
        return "first"
    # Fall through — Workday's "Name*" field is full-name; use first as sane default
    # since it's most commonly the only name field on cover-letter-style forms.
    return "first"


def _sub_key_for_contact(norm: str) -> str:
    if "email" in norm:
        return "email"
    if "country" in norm and ("code" in norm or "phone" in norm):
        return "country_phone_code"
    if "extension" in norm:
        return ""  # Workday phone-extension — leave blank
    if (
        "phone" in norm
        or "telephone" in norm
        or "mobile" in norm
        or "contact number" in norm
    ):
        return "phone_pretty"
    return "email"


def _sub_key_for_address(norm: str) -> str:
    if "country" in norm:
        return "country"
    if "state" in norm or "province" in norm or "region" in norm:
        return "state"
    if "zip" in norm or "postal" in norm:
        return "zip"
    if "city" in norm or "town" in norm:
        return "city"
    if "line 2" in norm:
        return "street2"
    if "address" in norm or "street" in norm or "line 1" in norm:
        return "street1"
    return "street1"


def _sub_key_for_links(norm: str) -> str:
    if "linkedin" in norm:
        return "linkedin_url"
    if "github" in norm:
        return "github_url"
    if "facebook" in norm or "twitter" in norm:
        return ""  # leave blank
    return "website_url"


def _sub_key_for_education(norm: str) -> str:
    if (
        "school" in norm
        or "university" in norm
        or "college" in norm
        or "institution" in norm
    ):
        return "school"
    if "field" in norm or "major" in norm or "discipline" in norm:
        return "field"
    if "degree" in norm or "level of education" in norm:
        return "degree"
    if "gpa" in norm or "grade" in norm:
        return "gpa"
    if "year" in norm or "graduation" in norm:
        return "graduation_year"
    return "school"


def _sub_key_for_account(norm: str) -> str:
    # password_lookup_path is the answer-bank's pointer to data/applications/
    # credentials.toml (#333) — fill_application's matcher hits this and the
    # session-level credential lookup wiring (#341, blocked behind #319) is
    # the consumer that turns "matched, here's the pointer" into "user typed
    # the per-ATS password from credentials.toml".
    if "verify" in norm or "confirm" in norm or "password" in norm:
        return "password_lookup_path"
    if "remember me" in norm:
        return ""  # boolean — caller handles
    return ""


def _sub_key_for_profile_fields(norm: str) -> str:
    if "headline" in norm:
        return "headline"
    if "pronoun" in norm:
        return "preferred_pronouns"
    if "summary" in norm:
        return "summary"
    return ""


def _sub_key_for_preferences(norm: str) -> str:
    # Order matters: more-specific patterns first.
    if "compensation align" in norm:
        return "compensation_alignment"
    if "salary" in norm or "compensation" in norm:
        return "salary_expectation_usd"
    if "start date" in norm or "earliest start" in norm or "available to start" in norm:
        return "earliest_start_date"
    if "notice" in norm:
        return "notice_period_days"
    if "relocat" in norm:
        return "willing_to_relocate"
    if (
        "remote" in norm
        or "hybrid" in norm
        or "onsite" in norm
        or "location preference" in norm
    ):
        return "remote_preference"
    if "travel" in norm:
        return "travel_pct_ok"
    return ""


def _sub_key_for_work_authorization(norm: str) -> str:
    if "sponsor" in norm:
        return "sponsorship_needed"
    if "visa" in norm or "immigration" in norm:
        return "visa_status"
    if "authorized" in norm or "right to work" in norm or "legally" in norm:
        return "authorized_us"
    return ""


def _sub_key_for_eeo(norm: str) -> str:
    if "gender" in norm or norm == "sex":
        return "gender"
    if "hispanic" in norm or "latino" in norm:
        return "hispanic_or_latino"
    if "race" in norm or "ethnic" in norm:
        return "race_ethnicity"
    if "veteran" in norm:
        return "veteran_status"
    if "disabil" in norm:
        return "disability_status"
    # "I do not want to answer" etc. — generic decline-to-answer; the caller
    # has to choose which EEO field to apply it to from context.
    return ""


def _sub_key_for_referral(norm: str) -> str:
    if "referred by" in norm or "referrer" in norm:
        return "referrer_name"
    if (
        "how did you hear" in norm
        or "how did you find" in norm
        or "source" in norm
        or "referral" in norm
    ):
        return "source"
    return ""


def _sub_key_for_consent(norm: str) -> str:
    if "terms" in norm:
        return "terms_of_use_agreed"
    if "privacy" in norm or "acknowledg" in norm:
        return "privacy_notice_acknowledged"
    if "marketing" in norm or "job alert" in norm:
        return "job_alerts_marketing"
    return ""


# Sections whose value is a simple string keyed by the section's only value field.
# When we match into one of these, the sub_key is fixed (only one fillable key).
_SINGLE_VALUE_SECTIONS = {
    "age_check": "answer",
}


# Sections we know how to route into sub-keys. Every multi-field section
# below MUST have a resolver — the generic fallback is intentionally
# fail-closed when a section has multiple fillable keys (see match()
# implementation below) to prevent confidently-wrong picks like
# "travel requirements" → preferences.salary_expectation_usd just because
# it's first in TOML order.
_SUB_KEY_RESOLVERS = {
    "name": _sub_key_for_name,
    "contact": _sub_key_for_contact,
    "address": _sub_key_for_address,
    "links": _sub_key_for_links,
    "education": _sub_key_for_education,
    "account": _sub_key_for_account,
    "profile_fields": _sub_key_for_profile_fields,
    "preferences": _sub_key_for_preferences,
    "work_authorization": _sub_key_for_work_authorization,
    "eeo": _sub_key_for_eeo,
    "referral": _sub_key_for_referral,
    "consent": _sub_key_for_consent,
}


# Sections we ignore for matching (they're not fill targets).
_NON_FILL_SECTIONS = {"honeypot", "custom", "work_experience"}
# work_experience is structural — the per-role loop is a Phase B concern,
# not a single-field fill. Skipped here so we don't try to fill labels like
# "Job Title*" or "Role Description" with the wrong value.


# -----------------------------
# The matcher
# -----------------------------


def _synonym_matches(syn: str, norm_label: str) -> bool:
    """Match a synonym against an already-normalized label.

    Two-tier:
      1. exact-equals (high confidence) — handles `First Name*` → `first name`
         after normalization strips the `*`.
      2. synonym appears as a *whole-word* substring of the label — handles
         `LinkedIn profile` matching synonym `linkedin`.

    The reverse direction (label as substring of synonym) is intentionally
    NOT allowed: it lets a short label like `Country` falsely match a
    longer synonym like `country phone code`. Whole-word boundary on the
    forward direction prevents `gpa` matching `gpan` etc.
    """
    syn_n = normalize(syn)
    if not syn_n:
        return False
    if syn_n == norm_label:
        return True
    if re.search(rf"\b{re.escape(syn_n)}\b", norm_label):
        return True
    return False


def match(label: str, answer_bank: dict[str, Any]) -> Decision:
    """Decide what to do with a single form field given its label.

    Returns either a Match (section, sub_key, value, matched_synonym) or
    a Skip (reason, detail).
    """
    if not label or not label.strip():
        return Skip(reason="no-match", detail="empty label")

    if is_honeypot(label):
        return Skip(reason="honeypot", detail=label[:80])

    norm = normalize(label)

    # Walk every section's synonyms list.
    for section, data in answer_bank.items():
        if section in _NON_FILL_SECTIONS:
            continue
        if not isinstance(data, dict):
            continue
        synonyms = data.get("synonyms")
        if not synonyms:
            continue
        for syn in synonyms:
            if _synonym_matches(syn, norm):
                # Resolve sub-key.
                if section in _SINGLE_VALUE_SECTIONS:
                    sub_key = _SINGLE_VALUE_SECTIONS[section]
                elif section in _SUB_KEY_RESOLVERS:
                    sub_key = _SUB_KEY_RESOLVERS[section](norm)
                else:
                    # Generic fallback for sections with NO registered
                    # resolver. Pick the only fillable key in the section
                    # (excluding "synonyms" + None / empty-string values).
                    # If there are multiple candidate keys, fail closed —
                    # confidently picking the first-in-TOML-order would
                    # mis-route labels (e.g. "travel requirements" landing
                    # on preferences.salary_expectation_usd). Add a
                    # section-specific resolver to _SUB_KEY_RESOLVERS rather
                    # than relying on this fallback for multi-field sections.
                    candidates = [
                        k
                        for k, v in data.items()
                        if k != "synonyms"
                        and v is not None
                        and (not isinstance(v, str) or v.strip())
                    ]
                    if len(candidates) == 1:
                        sub_key = candidates[0]
                    elif not candidates:
                        # Section has zero fillable keys — the bank is empty
                        # for this section, not a matcher gap. Remediation
                        # is "fill the bank", same as a per-key blank.
                        return Skip(
                            reason="empty-value",
                            detail=f"section={section} has no fillable keys",
                        )
                    else:
                        # `unresolved-sub-key` (not `empty-value`) so replay
                        # summaries point the operator at the matcher rather
                        # than the answer bank — the bank entries may be
                        # perfectly fillable, the matcher just doesn't know
                        # which one to pick.
                        return Skip(
                            reason="unresolved-sub-key",
                            detail=(
                                f"section={section} has {len(candidates)} "
                                "fillable keys but no resolver; add one to "
                                "_SUB_KEY_RESOLVERS to disambiguate"
                            ),
                        )
                if not sub_key:
                    # Resolver matched the section but returned "" — its
                    # heuristic branches didn't recognize this label. Same
                    # "extend the matcher" remediation as the fail-closed
                    # case above, not a bank-entry problem.
                    return Skip(
                        reason="unresolved-sub-key",
                        detail=f"matched section={section} but no fillable sub-key for label",
                    )
                value = data.get(sub_key)
                # Empty-value gate: skip if the resolved sub_key is None,
                # blank string, or whitespace-only string. Bools/numbers
                # always pass (caller stringifies for display).
                if value is None or (isinstance(value, str) and not value.strip()):
                    return Skip(
                        reason="empty-value",
                        detail=f"section={section}, sub_key={sub_key} is blank in answer bank",
                    )
                return Match(
                    section=section,
                    sub_key=sub_key,
                    value=str(value),
                    matched_synonym=syn,
                )

    return Skip(reason="no-match", detail=norm[:80])
