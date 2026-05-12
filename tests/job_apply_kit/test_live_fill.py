"""Tests for `job_apply_kit.live_fill` (#363).

Three concerns:

1. **`decide_fill`** — the gate. Parametric matrix covering every
   `(section, sub_key, skip_reason, live, allowed_sections)` shape
   that fill_application can hand in. Hard safety rails (honeypot /
   account / work_experience) verified to take precedence over the
   live + section flags.
2. **`parse_type_delay_range`** — string → (min, max) parsing with
   the error cases that argparse delegates to us.
3. **`pick_typing_delay`** — seeded RNG produces deterministic
   values inside the bounds.
"""

from __future__ import annotations

import random

import pytest

from job_apply_kit import (
    decide_fill,
    parse_type_delay_range,
    pick_typing_delay,
)

# Default "safe" subset the CLI ships with — keep this in sync with
# the fill_application.py default if it changes.
_SAFE_SECTIONS = frozenset({"name", "contact", "address", "links", "education"})
_ALL_SECTIONS = frozenset(
    {
        "name",
        "contact",
        "address",
        "links",
        "education",
        "account",
        "profile_fields",
        "preferences",
        "work_authorization",
        "eeo",
        "referral",
        "consent",
        "age_check",
    }
)


class TestDecideFillHardRails:
    """Honeypot / account / work_experience are NEVER filled,
    regardless of live mode + section whitelist. These are the
    #341 / #319 / threat-model invariants."""

    def test_honeypot_skip_reason_always_skips(self) -> None:
        # Even with live=True and an unrestricted section whitelist,
        # honeypot Skip decisions never fill.
        result = decide_fill(
            section=None,
            sub_key=None,
            skip_reason="honeypot",
            live=True,
            allowed_sections=_ALL_SECTIONS,
        )
        assert result == "skip-honeypot"

    def test_account_password_lookup_routes_to_credential_hook(
        self,
    ) -> None:
        # Match on account.password_lookup_path returns skip-account
        # so the caller dispatches to the #341 credential hook
        # instead of typing the bank value.
        result = decide_fill(
            section="account",
            sub_key="password_lookup_path",
            skip_reason=None,
            live=True,
            allowed_sections=_ALL_SECTIONS | {"account"},
        )
        assert result == "skip-account"

    def test_work_experience_always_skipped(self) -> None:
        # work_experience needs the per-role loop (Phase 3-C) — never
        # autofill the first instance.
        result = decide_fill(
            section="work_experience",
            sub_key="company",
            skip_reason=None,
            live=True,
            allowed_sections=_ALL_SECTIONS | {"work_experience"},
        )
        assert result == "skip-work-experience"

    def test_honeypot_section_always_skipped(self) -> None:
        # In addition to the skip_reason="honeypot" path, the
        # _NON_FILL_SECTIONS list in label_matcher excludes
        # honeypot from matching — but if a future synonym change
        # ever puts a section="honeypot" Match through this gate,
        # we still hard-skip.
        result = decide_fill(
            section="honeypot",
            sub_key="value",
            skip_reason=None,
            live=True,
            allowed_sections=_ALL_SECTIONS | {"honeypot"},
        )
        assert result == "skip-honeypot"


class TestDecideFillSkipReasons:
    """Skip decisions from the matcher (other than honeypot) all
    surface as 'skip-unfillable' — log only, no fill, no fancy
    routing."""

    @pytest.mark.parametrize(
        "reason",
        ["empty-value", "unresolved-sub-key", "intentional-skip", "no-match"],
    )
    def test_matcher_skip_reasons_are_unfillable(self, reason: str) -> None:
        result = decide_fill(
            section=None,
            sub_key=None,
            skip_reason=reason,
            live=True,
            allowed_sections=_ALL_SECTIONS,
        )
        assert result == "skip-unfillable"


class TestDecideFillLiveGate:
    """When live=False, every Match becomes 'skip-dry-run' (the
    current Phase 3-A behavior). When live=True, the section
    whitelist gates fills."""

    def test_dry_run_skips_match_regardless_of_section(self) -> None:
        result = decide_fill(
            section="name",
            sub_key="first",
            skip_reason=None,
            live=False,
            allowed_sections=_SAFE_SECTIONS,
        )
        assert result == "skip-dry-run"

    def test_live_fills_allowed_section(self) -> None:
        result = decide_fill(
            section="name",
            sub_key="first",
            skip_reason=None,
            live=True,
            allowed_sections=_SAFE_SECTIONS,
        )
        assert result == "fill"

    def test_live_skips_section_not_in_whitelist(self) -> None:
        # `eeo` is not in the default safe subset — user must opt
        # in via --fill-sections.
        result = decide_fill(
            section="eeo",
            sub_key="gender",
            skip_reason=None,
            live=True,
            allowed_sections=_SAFE_SECTIONS,
        )
        assert result == "skip-section-gated"

    def test_live_fills_eeo_when_opted_in(self) -> None:
        result = decide_fill(
            section="eeo",
            sub_key="gender",
            skip_reason=None,
            live=True,
            allowed_sections=_SAFE_SECTIONS | {"eeo"},
        )
        assert result == "fill"

    def test_live_skips_unknown_section(self) -> None:
        # A section that exists in the bank but is not in the
        # CLI-allowed set should be section-gated, not filled.
        result = decide_fill(
            section="something_custom",
            sub_key="x",
            skip_reason=None,
            live=True,
            allowed_sections=_SAFE_SECTIONS,
        )
        assert result == "skip-section-gated"


class TestDecideFillEdgeCases:
    def test_match_with_none_section_skips(self) -> None:
        # Defensive: should not happen in practice (matcher always
        # sets section on Match) but verify we don't try to fill
        # something with no section.
        result = decide_fill(
            section=None,
            sub_key="first",
            skip_reason=None,
            live=True,
            allowed_sections=_ALL_SECTIONS,
        )
        assert result == "skip-section-gated"

    def test_empty_allowed_sections_blocks_all(self) -> None:
        # `--fill-sections ""` (or unset combined with no defaults)
        # → every fill is section-gated, effectively making --live
        # a no-op until the user opts in to specific sections.
        result = decide_fill(
            section="name",
            sub_key="first",
            skip_reason=None,
            live=True,
            allowed_sections=frozenset(),
        )
        assert result == "skip-section-gated"


class TestParseTypeDelayRange:
    def test_basic_range(self) -> None:
        assert parse_type_delay_range("50-150") == (50, 150)

    def test_zero_range(self) -> None:
        # Edge case: zero-delay (instant fill) is allowed if the
        # user explicitly opts in — they may be testing on a local
        # fixture where bot detection doesn't matter.
        assert parse_type_delay_range("0-0") == (0, 0)

    def test_equal_min_max(self) -> None:
        # No jitter — fixed delay.
        assert parse_type_delay_range("100-100") == (100, 100)

    def test_missing_dash(self) -> None:
        with pytest.raises(ValueError, match="MIN-MAX"):
            parse_type_delay_range("100")

    def test_non_integer_sides(self) -> None:
        with pytest.raises(ValueError, match="integers"):
            parse_type_delay_range("abc-150")

    def test_negative_min(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            parse_type_delay_range("-10-150")

    def test_min_greater_than_max(self) -> None:
        with pytest.raises(ValueError, match="min must be <= max"):
            parse_type_delay_range("200-50")


class TestPickTypingDelay:
    def test_returns_value_in_range(self) -> None:
        rng = random.Random(42)
        for _ in range(50):
            value = pick_typing_delay((50, 150), rng)
            assert 50 <= value <= 150

    def test_deterministic_with_seeded_rng(self) -> None:
        # Same seed → same sequence.
        a = random.Random(0)
        b = random.Random(0)
        seq_a = [pick_typing_delay((10, 100), a) for _ in range(5)]
        seq_b = [pick_typing_delay((10, 100), b) for _ in range(5)]
        assert seq_a == seq_b

    def test_zero_range_returns_zero(self) -> None:
        rng = random.Random()
        assert pick_typing_delay((0, 0), rng) == 0
