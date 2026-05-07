"""Cover letter document IR composition.

Defines the canonical sections of a cover letter (sender block, date,
recipient block, greeting, opening, body paragraphs, closing paragraph,
sign-off, signature) and a markdown serializer used by both the
HTML/MD review outputs and the DOCX/PDF renderers in
``cover_letter_export``.

This module performs no LLM calls and no I/O beyond the inputs handed
to ``compose_cover_letter``.
"""

from __future__ import annotations

import datetime as _dt
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input

DEFAULT_ADDRESSEE_FALLBACK = "Hiring Team"
DEFAULT_CLOSING = "Sincerely,"


@dataclass(frozen=True)
class CoverLetterPreferences:
    closing: str = DEFAULT_CLOSING
    addressee_fallback: str = DEFAULT_ADDRESSEE_FALLBACK


@dataclass(frozen=True)
class CoverLetterBody:
    opening: str
    body_paragraphs: tuple[str, ...]
    closing_paragraph: str

    def all_paragraphs(self) -> tuple[str, ...]:
        return (self.opening, *self.body_paragraphs, self.closing_paragraph)


@dataclass(frozen=True)
class CoverLetterIR:
    sender_name: str
    sender_lines: tuple[str, ...]
    date_line: str
    recipient_lines: tuple[str, ...]
    greeting: str
    body: CoverLetterBody
    closing: str

    def word_count(self) -> int:
        return sum(len(p.split()) for p in self.body.all_paragraphs())


def load_cover_letter_preferences(
    profile_payload: dict[str, Any],
) -> CoverLetterPreferences:
    """Read optional ``[cover_letter]`` table from a parsed profile payload.

    Missing table or missing keys fall back to module defaults.
    """
    raw = profile_payload.get("cover_letter", {})
    if not isinstance(raw, dict):
        return CoverLetterPreferences()
    closing = str(raw.get("closing", DEFAULT_CLOSING)).strip() or DEFAULT_CLOSING
    fallback = (
        str(raw.get("addressee_fallback", DEFAULT_ADDRESSEE_FALLBACK)).strip()
        or DEFAULT_ADDRESSEE_FALLBACK
    )
    return CoverLetterPreferences(closing=closing, addressee_fallback=fallback)


def read_profile_payload(path: Path) -> dict[str, Any]:
    assert_not_blocked_runtime_input(path)
    with path.open("rb") as handle:
        return tomllib.load(handle)


def format_date(today: _dt.date) -> str:
    return f"{today.strftime('%B')} {today.day}, {today.year}"


def _build_sender_lines(profile: Any) -> tuple[str, ...]:
    """Return the small contact stack under the sender's name.

    Deliberately picks: location, email, phone, plus one of website /
    linkedin / github (in that order). Empty fields are dropped.
    Linkedin slug is rendered as ``linkedin.com/in/<slug>``; github
    handle as ``github.com/<handle>``.
    """
    lines: list[str] = []
    location = (getattr(profile, "location", "") or "").strip()
    if location:
        lines.append(location)
    email = (getattr(profile, "email", "") or "").strip()
    phone = (getattr(profile, "phone", "") or "").strip()
    contact = [c for c in (email, phone) if c]
    if contact:
        lines.append(" | ".join(contact))
    website = (getattr(profile, "website", "") or "").strip()
    linkedin = (getattr(profile, "linkedin", "") or "").strip()
    github = (getattr(profile, "github", "") or "").strip()
    if website:
        lines.append(website)
    elif linkedin:
        lines.append(f"linkedin.com/in/{linkedin}")
    elif github:
        lines.append(f"github.com/{github}")
    return tuple(lines)


def _build_recipient_lines(addressee: str, company_name: str) -> tuple[str, ...]:
    company = (company_name or "").strip()
    addr = (addressee or "").strip()
    if company:
        return (addr, company) if addr else (company,)
    return (addr,) if addr else ()


def compose_cover_letter(
    *,
    profile: Any,
    addressee: str,
    company_name: str,
    body: CoverLetterBody,
    preferences: CoverLetterPreferences,
    today: _dt.date | None = None,
) -> CoverLetterIR:
    today = today or _dt.date.today()
    return CoverLetterIR(
        sender_name=(getattr(profile, "name", "") or "").strip(),
        sender_lines=_build_sender_lines(profile),
        date_line=format_date(today),
        recipient_lines=_build_recipient_lines(addressee, company_name),
        greeting=f"Dear {addressee},",
        body=body,
        closing=preferences.closing,
    )


def render_markdown(ir: CoverLetterIR) -> str:
    """Serialize the IR to a markdown body the renderers consume.

    Layout is plain paragraph text — no headings, no bullets — so the
    cover-letter renderers can apply letter formatting consistently
    while review-mode (``--outputs md,html``) gets a readable text
    artifact.
    """
    parts: list[str] = []
    if ir.sender_name:
        parts.append(ir.sender_name)
    parts.extend(line for line in ir.sender_lines if line)
    parts.append("")
    parts.append(ir.date_line)
    parts.append("")
    parts.extend(line for line in ir.recipient_lines if line)
    parts.append("")
    parts.append(ir.greeting)
    parts.append("")
    for paragraph in ir.body.all_paragraphs():
        text = paragraph.strip()
        if not text:
            continue
        parts.append(text)
        parts.append("")
    parts.append(ir.closing)
    parts.append("")
    if ir.sender_name:
        parts.append(ir.sender_name)
    while parts and parts[-1] == "":
        parts.pop()
    return "\n".join(parts) + "\n"
