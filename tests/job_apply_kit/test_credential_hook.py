"""Tests for `job_apply_kit.credential_hook.handle_credential_match`.

Three primary paths:

  1. **Saved-credential** — `lookup()` finds an entry; the hook
     returns it with `displayed=True`, no `record()` is called, no
     prompts fire.
  2. **New-tenant** — `lookup()` returns `None`; the hook prompts for
     username + password and persists via `record()` with
     `recorded=True`. The on-disk file is chmod 0600.
  3. **Unknown-ATS / unknown-tenant** — `infer_ats_tenant` returned
     `(None, None)`; the prompter is asked to supply both before
     proceeding into path 1 or 2.

Tests inject a `FakePrompter` that returns canned answers and records
every call, so prompt sequences are explicit and asserted.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from job_apply_kit import (
    CredentialResult,
    handle_credential_match,
)
from resume_builder import credential_store


class FakePrompter:
    """Canned-response stand-in for `CredentialPrompter`."""

    def __init__(self, answers: list[str], secrets: list[str]) -> None:
        self._answers = list(answers)
        self._secrets = list(secrets)
        self.asked: list[str] = []
        self.asked_secret: list[str] = []

    def ask(self, prompt: str) -> str:
        self.asked.append(prompt)
        if not self._answers:
            raise AssertionError(
                f"FakePrompter.ask called with no remaining answers; prompt={prompt!r}"
            )
        return self._answers.pop(0)

    def ask_secret(self, prompt: str) -> str:
        self.asked_secret.append(prompt)
        if not self._secrets:
            raise AssertionError(
                f"FakePrompter.ask_secret called with no remaining secrets; "
                f"prompt={prompt!r}"
            )
        return self._secrets.pop(0)


@pytest.fixture
def creds_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated credentials.toml under tmp_path.

    `credential_store` enforces a runtime-guard against blocked roots;
    `tmp_path` (which lives under `/tmp`) is not blocked, so the real
    `record` / `lookup` functions can run unmodified.
    """
    return tmp_path / "credentials.toml"


class TestSavedCredentialPath:
    """When the credential already exists, the hook displays it and
    does not prompt or write anything."""

    def test_returns_saved_entry(self, creds_path: Path) -> None:
        # Seed a saved credential by calling record() directly.
        credential_store.record(
            "workday",
            "becu",
            "jane@example.com",
            "S3cret!",
            path=creds_path,
        )

        prompter = FakePrompter(answers=[], secrets=[])
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="https://becu.wd1.myworkdayjobs.com/Apply/job/123",
            prompter=prompter,
            credentials_path=creds_path,
        )

        assert isinstance(result, CredentialResult)
        assert result.displayed is True
        assert result.recorded is False
        assert result.ats == "workday"
        assert result.tenant == "becu"
        assert result.username == "jane@example.com"
        assert result.password == "S3cret!"
        assert "CREDENTIAL (saved)" in result.message
        assert "S3cret!" in result.message
        # No prompts should have fired — ATS+tenant were supplied and
        # the credential existed.
        assert prompter.asked == []
        assert prompter.asked_secret == []


class TestNewTenantPath:
    """When `lookup()` returns None, the hook prompts for credentials
    and persists them via `record()` (mode 0600)."""

    def test_prompts_and_records(self, creds_path: Path) -> None:
        prompter = FakePrompter(
            answers=["new-user@example.com"],
            secrets=["NewPass123!"],
        )

        result = handle_credential_match(
            ats="workable",
            tenant="murmuration",
            page_url="https://apply.workable.com/murmuration/j/ABCD/",
            prompter=prompter,
            credentials_path=creds_path,
        )

        assert result.displayed is False
        assert result.recorded is True
        assert result.username == "new-user@example.com"
        assert result.password == "NewPass123!"
        assert "newly recorded" in result.message
        # Exactly one plain-text prompt (username) + one secret prompt.
        assert len(prompter.asked) == 1
        assert len(prompter.asked_secret) == 1

        # Persistence: the credential is now readable and the file is
        # mode 0600 per credential_store's contract.
        roundtrip = credential_store.lookup("workable", "murmuration", path=creds_path)
        assert roundtrip is not None
        assert roundtrip["username"] == "new-user@example.com"
        assert roundtrip["password"] == "NewPass123!"
        assert roundtrip.get("tenant_url") == (
            "https://apply.workable.com/murmuration/j/ABCD/"
        )
        assert (os.stat(creds_path).st_mode & 0o777) == 0o600

    def test_subsequent_lookup_finds_recorded_credential(
        self, creds_path: Path
    ) -> None:
        """After a new-tenant prompt, the *next* hook invocation for
        the same `(ats, tenant)` should hit the saved-credential path."""
        prompter = FakePrompter(
            answers=["x@example.com"],
            secrets=["pw"],
        )
        handle_credential_match(
            ats="greenhouse",
            tenant="acme",
            page_url="https://boards.greenhouse.io/acme/jobs/1",
            prompter=prompter,
            credentials_path=creds_path,
        )

        prompter2 = FakePrompter(answers=[], secrets=[])
        result2 = handle_credential_match(
            ats="greenhouse",
            tenant="acme",
            page_url="https://boards.greenhouse.io/acme/jobs/2",
            prompter=prompter2,
            credentials_path=creds_path,
        )
        assert result2.displayed is True
        assert result2.recorded is False
        assert result2.password == "pw"
        assert prompter2.asked == []
        assert prompter2.asked_secret == []


class TestUnknownAtsTenantPath:
    """When `infer_ats_tenant` returned (None, None), the hook should
    prompt the user for both before continuing."""

    def test_prompts_for_ats_and_tenant(self, creds_path: Path) -> None:
        # No saved credential — the hook should ask for ats, tenant,
        # then username, then password.
        prompter = FakePrompter(
            answers=["icims", "careers-acme", "u@example.com"],
            secrets=["pw!"],
        )
        result = handle_credential_match(
            ats=None,
            tenant=None,
            page_url="https://careers-acme.icims.com/jobs/1",
            prompter=prompter,
            credentials_path=creds_path,
        )

        assert result.ats == "icims"
        # credential_store.normalize_key collapses hyphens to
        # underscores, so the canonical tenant slug is "careers_acme"
        # even though the user typed "careers-acme". (PR #361 review 2.)
        assert result.tenant == "careers_acme"
        assert result.recorded is True
        # First two prompts were for the unknown ats/tenant; third for
        # the username.
        assert len(prompter.asked) == 3
        assert len(prompter.asked_secret) == 1

    def test_unknown_ats_only(self, creds_path: Path) -> None:
        # Tenant is known but ATS isn't — only the ATS gets prompted.
        prompter = FakePrompter(
            answers=["workday", "u@example.com"],
            secrets=["pw"],
        )
        result = handle_credential_match(
            ats=None,
            tenant="becu",
            page_url="https://becu.wd1.myworkdayjobs.com/x",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.ats == "workday"
        assert result.tenant == "becu"
        # ATS prompt + username prompt = 2 plain-text asks.
        assert len(prompter.asked) == 2
        assert len(prompter.asked_secret) == 1


class TestEmptyPromptHandling:
    """The hook re-prompts on empty user input (up to 3 attempts) and
    raises ValueError after that, so a slip of the Enter key doesn't
    crash mid-form via credential_store's empty-key ValueError. (PR
    #361 review.)
    """

    def test_empty_ats_retries_then_succeeds(self, creds_path: Path) -> None:
        # Two empty answers then a real one for the ATS, then real
        # answers for tenant + username + password.
        prompter = FakePrompter(
            answers=["", "", "workday", "becu", "u@example.com"],
            secrets=["pw"],
        )
        result = handle_credential_match(
            ats=None,
            tenant=None,
            page_url="https://example/x",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.ats == "workday"
        assert result.tenant == "becu"

    def test_empty_ats_after_3_attempts_raises(self, creds_path: Path) -> None:
        prompter = FakePrompter(
            answers=["", "", ""],
            secrets=[],
        )
        with pytest.raises(ValueError, match="empty ATS slug"):
            handle_credential_match(
                ats=None,
                tenant="becu",
                page_url="",
                prompter=prompter,
                credentials_path=creds_path,
            )

    def test_empty_password_retries_then_succeeds(self, creds_path: Path) -> None:
        # The password prompt routes through ask_secret; empty inputs
        # there also retry up to 3 times.
        prompter = FakePrompter(
            answers=["u@example.com"],
            secrets=["", "real-password"],
        )
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="https://x",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.password == "real-password"
        assert result.recorded is True

    def test_whitespace_only_password_retries(self, creds_path: Path) -> None:
        # An all-whitespace password would be recorded (no strip on
        # secrets) and then immediately fail the saved-credential
        # validation on the next lookup, causing a re-prompt loop.
        # Reject at prompt time. (PR #361 review round 3.)
        prompter = FakePrompter(
            answers=["u@example.com"],
            secrets=["   ", "\t\n", "real-pw"],
        )
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.password == "real-pw"
        # All three secret prompts fired (2 rejected + 1 accepted).
        assert len(prompter.asked_secret) == 3

    def test_password_with_surrounding_whitespace_preserved(
        self, creds_path: Path
    ) -> None:
        # Whitespace AROUND a real password is meaningful (some
        # credentials happen to have it) — don't strip on secrets.
        prompter = FakePrompter(
            answers=["u@example.com"],
            secrets=["  S3cret!  "],
        )
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.password == "  S3cret!  "
        # And it round-trips through credential_store unchanged.
        entry = credential_store.lookup("workday", "becu", path=creds_path)
        assert entry is not None
        assert entry["password"] == "  S3cret!  "


class TestPasswordReprSafety:
    """`CredentialResult` must not leak the password through dataclass
    repr (which would propagate it into tracebacks and accidental
    logging). PR #361 review."""

    def test_password_not_in_repr(self, creds_path: Path) -> None:
        credential_store.record(
            "workday", "becu", "u@x.com", "SuperSecret", path=creds_path
        )
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="",
            prompter=FakePrompter(answers=[], secrets=[]),
            credentials_path=creds_path,
        )
        rendered = repr(result)
        assert "SuperSecret" not in rendered, (
            "CredentialResult repr must not contain the raw password"
        )
        # Other fields should still appear so the repr remains useful
        # for debugging.
        assert "workday" in rendered
        assert "becu" in rendered

    def test_password_still_accessible_via_attribute(self, creds_path: Path) -> None:
        # Tests + production callers (banner formatting) still read
        # `.password` directly. Confirm the field is present and
        # holds the cleartext value, just not in repr.
        credential_store.record("workday", "becu", "u@x.com", "P", path=creds_path)
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="",
            prompter=FakePrompter(answers=[], secrets=[]),
            credentials_path=creds_path,
        )
        assert result.password == "P"


class TestNormalization:
    """`credential_store` normalizes ats/tenant keys internally
    (lowercase + punctuation collapsed). The hook applies the same
    normalization to its return values so the caller's dedupe key
    matches across raw-input vs inferred-input variations. (PR #361
    review round 2.)
    """

    def test_user_entered_mixed_case_ats_is_canonicalized(
        self, creds_path: Path
    ) -> None:
        # User types "Workday" (mixed case) while inference later
        # would yield "workday". Result must use the canonical slug
        # so dedupe doesn't fire twice.
        credential_store.record("workday", "becu", "u@x.com", "P", path=creds_path)
        result = handle_credential_match(
            ats="Workday",
            tenant="BECU",
            page_url="",
            prompter=FakePrompter(answers=[], secrets=[]),
            credentials_path=creds_path,
        )
        assert result.ats == "workday"
        assert result.tenant == "becu"

    def test_punctuation_tenant_normalizes(self, creds_path: Path) -> None:
        # `careers_acme` vs `careers-acme` — credential_store collapses
        # both to the same slug; the hook should report the slug.
        prompter = FakePrompter(answers=["u@x.com"], secrets=["pw"])
        result = handle_credential_match(
            ats="icims",
            tenant="careers-acme",
            page_url="",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.tenant == "careers_acme"


class TestCorruptSavedEntry:
    """The credentials file is user-editable, so saved entries can
    have missing or empty username/password. Treat as a miss and
    fall back to the prompt+record flow. (PR #361 review round 2.)
    """

    def test_entry_missing_password_falls_back_to_prompt(
        self, creds_path: Path
    ) -> None:
        # Seed an entry with no password field at all (simulating a
        # hand-edit that dropped the line).
        credential_store.record("workday", "becu", "u@x.com", "P", path=creds_path)
        # Now corrupt: rewrite with no password.
        import tomli_w

        with creds_path.open("rb") as f:
            import tomllib

            data = tomllib.load(f)
        data["ats"]["workday"]["becu"].pop("password")
        creds_path.write_text(tomli_w.dumps(data), encoding="utf-8")

        prompter = FakePrompter(answers=["new@x.com"], secrets=["new-pw"])
        result = handle_credential_match(
            ats="workday",
            tenant="becu",
            page_url="https://becu.wd1.myworkdayjobs.com/x",
            prompter=prompter,
            credentials_path=creds_path,
        )
        # Should have prompted (not displayed the corrupt entry).
        assert result.recorded is True
        assert result.displayed is False
        assert result.password == "new-pw"

    def test_entry_with_blank_username_falls_back(self, creds_path: Path) -> None:
        # Whitespace-only username — same fallback.
        credential_store.record("workable", "co", "   ", "real-pw", path=creds_path)
        prompter = FakePrompter(answers=["u@x.com"], secrets=["new-pw"])
        result = handle_credential_match(
            ats="workable",
            tenant="co",
            page_url="",
            prompter=prompter,
            credentials_path=creds_path,
        )
        assert result.recorded is True
        assert result.password == "new-pw"


class TestMessageContent:
    """The banner string is what the caller prints; verify it contains
    the key information so the user can act on it."""

    def test_saved_banner_includes_ats_tenant_and_credentials(
        self, creds_path: Path
    ) -> None:
        credential_store.record("workday", "wu", "user@x.com", "PW", path=creds_path)
        result = handle_credential_match(
            ats="workday",
            tenant="wu",
            page_url="https://wu.example/x",
            prompter=FakePrompter(answers=[], secrets=[]),
            credentials_path=creds_path,
        )
        assert "workday.wu" in result.message
        assert "user@x.com" in result.message
        assert "PW" in result.message
        assert "never autofill" in result.message.lower()
