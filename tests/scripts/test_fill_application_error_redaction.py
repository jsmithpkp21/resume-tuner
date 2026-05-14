"""Tests for live-fill error-message redaction (#365).

The redaction primitives `redact` and `redact_error_text` live in
`job_apply_kit.redaction` (moved out of `scripts/fill_application.py`
in this PR so tests can import them without dragging in the script's
top-level Playwright imports — those sys.exit(2) in environments
without Playwright, breaking pytest collection).

PR #364 review caught that `fill_application._perform_live_fill`'s
radio-group "no option matched" path embedded the raw answer-bank
value (gender, veteran status, etc.) into the error string. The
error is logged to terminal AND persisted to the fill-decisions
JSON, bypassing the `--show-values` redaction the success path
honors.

This file tests the redaction helpers + asserts the radio-group
error format uses the redacted form. End-to-end exercise through
`_perform_live_fill` would require mocking Playwright; the
unit-level helpers carry the privacy guarantee.
"""

from __future__ import annotations

from job_apply_kit.redaction import redact, redact_error_text


class TestRedact:
    """Sanity-check the redaction primitive. Contract: returns
    `<value len=N>` for any input, never the input itself."""

    def test_returns_length_fingerprint(self) -> None:
        assert redact("Male") == "<value len=4>"

    def test_does_not_contain_input(self) -> None:
        # The whole point: the input value never appears in the output.
        secret = "SuperSecret123!"
        assert secret not in redact(secret)

    def test_empty_string(self) -> None:
        assert redact("") == "<value len=0>"


class TestRedactErrorText:
    """`redact_error_text(text, sensitive)` substring-replaces the
    sensitive content with `redact(sensitive)`. Pure function."""

    def test_replaces_sensitive_when_present(self) -> None:
        out = redact_error_text(
            "TimeoutError: waiting for selector value='Male'", "Male"
        )
        assert "Male" not in out
        assert "<value len=4>" in out

    def test_multiple_occurrences_all_replaced(self) -> None:
        # If Playwright embeds the value twice (selector + error
        # context), both get scrubbed.
        out = redact_error_text("X X", "X")
        assert "X" not in out
        # Two redaction tokens.
        assert out.count("<value len=1>") == 2

    def test_returns_unchanged_when_not_present(self) -> None:
        msg = "TimeoutError: element not visible"
        assert redact_error_text(msg, "unrelated-value") == msg

    def test_empty_sensitive_returns_unchanged(self) -> None:
        msg = "TimeoutError: details"
        assert redact_error_text(msg, "") == msg

    def test_none_sensitive_returns_unchanged(self) -> None:
        msg = "TimeoutError: details"
        assert redact_error_text(msg, None) == msg

    def test_does_not_leak_input_anywhere(self) -> None:
        # Defense-in-depth: even if a future edit reshapes the output,
        # the sensitive value must never appear verbatim.
        secret = "HighlyConfidential"
        out = redact_error_text(f"failed: tried {secret} again", secret)
        assert secret not in out


class TestRadioGroupErrorFormat:
    """The format string used at the radio-group "no option matched"
    failure site in `fill_application._perform_live_fill` (#364 / #365).
    Verify the constructed message redacts the bank value."""

    def test_no_match_message_uses_redacted_value(self) -> None:
        # Reproduce the format string fill_application uses. If a
        # future refactor changes the wording, update both the call
        # site and this assertion together.
        value = "Veteran"
        message = f"no radio option matched ({redact(value)})"
        assert value not in message
        assert "<value len=7>" in message

    def test_redacted_form_distinguishes_value_lengths(self) -> None:
        # Two different sensitive values produce different
        # fingerprints — useful for debugging without leaking.
        m1 = f"no radio option matched ({redact('A')})"
        m2 = f"no radio option matched ({redact('AB')})"
        assert m1 != m2


class TestErrorRedactionContract:
    """Round-trip: an error message containing the value goes through
    `redact_error_text`, ends up without the value, and the redaction
    is detectable (len fingerprint present)."""

    def test_exception_path_redaction_roundtrip(self) -> None:
        # Simulate a Playwright exception that happens to embed the value.
        sensitive = "PII-answer-here"
        sim_exception_msg = f"TimeoutError: locator.fill(value='{sensitive}') timed out"
        redacted = redact_error_text(sim_exception_msg, sensitive)
        assert sensitive not in redacted
        assert "<value len=15>" in redacted
        # Diagnostic context preserved.
        assert "TimeoutError" in redacted
        assert "timed out" in redacted
