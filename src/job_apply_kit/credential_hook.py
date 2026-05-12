"""Credential-lookup hook for the application-submission filler.

Bridges `job_apply_kit.label_matcher` (which decides a password field
matched the `[account]` section) and `resume_builder.credential_store`
(which holds per-ATS saved credentials).

Purpose, in one line: when the matcher hits a password field on a live
apply page, look up the saved credential for the page's
`(ats, tenant)` and *display* it for the user to type — never autofill.
If no credential is saved, prompt the user and persist via
`credential_store.record`.

Display-only is intentional (#333 threat model): autofill risks typing
the password into a phishing imitation form, and Workday's bot
detection is also more sensitive to programmatic fills than to typed
input. The user is always in the loop.

Public API:

  - `CredentialPrompter` — Protocol the caller satisfies to provide
    interactive input. `fill_application.py` injects a wrapper around
    `input()` + `getpass.getpass()`; tests inject canned-response
    fakes.
  - `CredentialResult` — dataclass with the resolved credential plus
    bookkeeping flags + a formatted banner string the caller prints.
  - `handle_credential_match()` — the hook itself. Pure-ish: side
    effects are confined to `credential_store.record` (when a new
    credential is created) and the prompter calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from resume_builder import credential_store


class CredentialPrompter(Protocol):
    """Interactive-prompt protocol used by `handle_credential_match`.

    Two methods so the caller can route the password prompt through
    `getpass.getpass()` (no echo) while keeping plain-text prompts on
    `input()`. Tests inject a fake that returns pre-scripted answers.
    """

    def ask(self, prompt: str) -> str:
        """Ask for a plain-text value (e.g. ATS family, tenant, username)."""
        ...

    def ask_secret(self, prompt: str) -> str:
        """Ask for a secret (password). Implementations should disable echo."""
        ...


@dataclass(frozen=True)
class CredentialResult:
    """Outcome of a single credential-hook invocation."""

    ats: str
    tenant: str
    username: str
    password: str
    displayed: bool  # saved credential was found and printed
    recorded: bool  # a new credential was prompted-for and persisted
    message: str  # banner text the caller should print to terminal


def _banner(*, header: str, ats: str, tenant: str, lines: list[str]) -> str:
    """Format a multi-line attention banner the caller prints verbatim."""
    title = f"=== {header}: {ats}.{tenant} ==="
    body = "\n".join(lines)
    return f"\n{title}\n{body}\n{'=' * len(title)}\n"


def handle_credential_match(
    *,
    ats: str | None,
    tenant: str | None,
    page_url: str,
    prompter: CredentialPrompter,
    credentials_path: Path = credential_store.DEFAULT_CREDENTIALS_PATH,
) -> CredentialResult:
    """Run the credential lookup-or-record flow for a password field.

    Args:
        ats: ATS family slug as inferred by `ats_inference.infer_ats_tenant`,
            or `None` if inference didn't recognize the page. When `None`,
            the prompter is asked to supply it.
        tenant: Tenant slug; same `None`-fallback semantics as `ats`.
        page_url: The live page URL — recorded as `tenant_url` when
            persisting a new credential so the entry knows where it was
            captured.
        prompter: Interactive-prompt callback (see `CredentialPrompter`).
        credentials_path: Path to the credentials TOML. Defaults to
            `credential_store.DEFAULT_CREDENTIALS_PATH`.

    Returns:
        `CredentialResult` with the resolved credential and a banner
        string the caller should print. The caller is responsible for
        keeping the password off any on-disk capture / decisions log.
    """
    if not ats:
        ats = prompter.ask(
            "Could not infer ATS family from URL. Enter ATS slug "
            "(e.g. workday, workable, greenhouse, icims): "
        ).strip()
    if not tenant:
        tenant = prompter.ask(
            "Could not infer tenant from URL. Enter tenant slug "
            "(e.g. becu, murmuration): "
        ).strip()

    entry = credential_store.lookup(ats, tenant, path=credentials_path)
    if entry is not None:
        # Saved credential — display only, no record() call.
        username = str(entry.get("username", ""))
        password = str(entry.get("password", ""))
        message = _banner(
            header="CREDENTIAL (saved)",
            ats=ats,
            tenant=tenant,
            lines=[
                f"username: {username}",
                f"password: {password}",
                "",
                "Type the password into the live form (never autofill).",
            ],
        )
        return CredentialResult(
            ats=ats,
            tenant=tenant,
            username=username,
            password=password,
            displayed=True,
            recorded=False,
            message=message,
        )

    # No saved credential — prompt + record.
    username = prompter.ask(
        f"No saved credential for {ats}.{tenant}. Enter username/email: "
    ).strip()
    password = prompter.ask_secret(
        f"Enter password for {ats}.{tenant} (will be saved to {credentials_path}): "
    )
    credential_store.record(
        ats,
        tenant,
        username,
        password,
        tenant_url=page_url or None,
        path=credentials_path,
    )
    message = _banner(
        header="CREDENTIAL (newly recorded)",
        ats=ats,
        tenant=tenant,
        lines=[
            f"Saved to {credentials_path} (mode 0600).",
            f"username: {username}",
            f"password: {password}",
            "",
            "Type the password into the live form (never autofill).",
        ],
    )
    return CredentialResult(
        ats=ats,
        tenant=tenant,
        username=username,
        password=password,
        displayed=False,
        recorded=True,
        message=message,
    )
