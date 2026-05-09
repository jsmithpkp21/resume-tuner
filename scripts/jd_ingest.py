#!/usr/bin/env python3
"""Deterministic job-input ingestion for resume tailoring.

This module intentionally keeps behavior predictable for MVP:
- accept a job posting URL and parse stable hints from URL/query/title
- attempt lightweight page metadata fetch with graceful fallback
- produce low-risk deterministic company context scaffolding

Future phases can replace or augment this with richer provider adapters.
"""

from __future__ import annotations

import html as _html_lib
import ipaddress
import json
import logging
import os
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

# Use local import when run as `python scripts/jd_ingest.py`,
# and package import when loaded as `scripts.jd_ingest`.
if __package__ in {None, ""}:
    from _runtime_guard import assert_not_blocked_runtime_input
else:
    from scripts._runtime_guard import assert_not_blocked_runtime_input

_JOB_PAGE_FIXTURE_ENV = "RESUME_BUILDER_JOB_PAGE_FIXTURE"
_MAX_DESCRIPTION_EXCERPT = 500
_MAX_FETCH_BYTES = 256 * 1024

logger = logging.getLogger(__name__)

# Single User-Agent for every outbound fetch (HTML page fetcher AND JSON
# board-API fetcher). Centralized so updates can't drift between paths.
_FETCH_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Hosts that render the JD body via client-side JavaScript and have no
# public JSON board API (so the cheap static-HTML fetch + the API path
# both come back near-empty). Always-Playwright when the env var is set;
# the headless-browser path is the only way to recover JD content from
# these. See #247 fix #3.
_JS_RENDERED_HOST_FAMILIES: tuple[str, ...] = (
    "myworkdayjobs.com",  # Workday board family (e.g. *.wd1.myworkdayjobs.com)
    # Specific subdomain match — generic 'careers.<company>.com' patterns
    # often serve fine via static fetch + company-site URL fallback, so we
    # don't blanket-include them.
)
# Specific hostnames (exact match) that need the Playwright path. Used for
# entries that aren't part of a wildcard host family, like the Western Union
# careers portal which renders the JD body in client-side JS even though it
# lives on a vanity hostname.
_JS_RENDERED_EXACT_HOSTS: tuple[str, ...] = ("careers.westernunion.com",)

_PLAYWRIGHT_ENABLED_ENV = "RESUME_BUILDER_ENABLE_PLAYWRIGHT"
_PLAYWRIGHT_TIMEOUT_SECONDS = 15.0
# When the static fetch comes back below this many chars, retry via
# Playwright even if the host isn't in the allowlist. Catches new
# JS-rendered domains we haven't curated yet.
_PLAYWRIGHT_RETRY_THRESHOLD_CHARS = 200
# Settle-time after `domcontentloaded` for late-firing JS to finish
# rendering the JD body. Tuned conservatively — most boards finish
# rendering within ~1 s; 2 s leaves a margin without making the fetch
# painfully slow.
_PLAYWRIGHT_SETTLE_MS = 2000

# Hosts where a public JSON board API serves the JD body the static-HTML
# fetcher can't see (the page is JS-rendered). #247 fix #3 (partial).
_GREENHOUSE_BOARD_HOSTS: tuple[str, ...] = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
)


class _ValidatingRedirectHandler(HTTPRedirectHandler):
    """Validate each redirect target before following it."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        _validate_job_url(_normalize_url(newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class CompanyResearch:
    company_name: str
    industry_hint: str
    product_hint: str
    strategy: str
    confidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "company_name": self.company_name,
            "industry_hint": self.industry_hint,
            "product_hint": self.product_hint,
            "strategy": self.strategy,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class FetchedPage:
    status: str
    title: str
    description: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class JobContext:
    input_url: str
    normalized_url: str
    source: str
    role_hint: str
    company_name: str
    job_id: str
    fetch_status: str
    page_title: str
    description_excerpt: str
    notes: tuple[str, ...]
    company_research: CompanyResearch | None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "input_url": self.input_url,
            "normalized_url": self.normalized_url,
            "source": self.source,
            "role_hint": self.role_hint,
            "company_name": self.company_name,
            "job_id": self.job_id,
            "fetch_status": self.fetch_status,
            "page_title": self.page_title,
            "description_excerpt": self.description_excerpt,
            "notes": list(self.notes),
        }
        if self.company_research is not None:
            payload["company_research"] = self.company_research.to_dict()
        return payload


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title_parts: list[str] = []
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
            return
        if tag.lower() != "meta":
            return

        attrs_map = {key.lower(): (value or "") for key, value in attrs}
        name = attrs_map.get("name", "").lower()
        prop = attrs_map.get("property", "").lower()
        if name == "description" or prop == "og:description":
            content = attrs_map.get("content", "").strip()
            if content and not self.description:
                self.description = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(
            part.strip() for part in self.title_parts if part.strip()
        ).strip()


def ingest_job_context(
    job_url: str,
    fetcher: Callable[[str], FetchedPage] | None = None,
) -> JobContext:
    normalized_url = _normalize_url(job_url)
    _validate_job_url(normalized_url)
    parsed = urlparse(normalized_url)
    source = _infer_source(parsed.netloc)
    query = parse_qs(parsed.query)
    job_id = _extract_job_id(query, parsed.path)

    effective_fetcher = fetcher or _fetch_job_page_metadata
    fetched = effective_fetcher(normalized_url)

    role_hint = _extract_role_hint(
        query=query,
        path=parsed.path,
        source=source,
        page_title=fetched.title,
        description=fetched.description,
    )
    company_name = _extract_company_name(
        source=source,
        netloc=parsed.netloc,
        path=parsed.path,
        page_title=fetched.title,
        description=fetched.description,
    )

    research = _deterministic_company_research(company_name=company_name, source=source)

    return JobContext(
        input_url=job_url.strip(),
        normalized_url=normalized_url,
        source=source,
        role_hint=role_hint,
        company_name=company_name,
        job_id=job_id,
        fetch_status=fetched.status,
        page_title=fetched.title,
        description_excerpt=_truncate_excerpt(fetched.description),
        notes=fetched.notes,
        company_research=research,
    )


def ingest_job_text(job_text: str, source_hint: str = "job-text-file") -> JobContext:
    text = job_text.strip()
    role_hint = _extract_role_from_text_blob(text)
    company_name = _extract_company_from_text_blob(text)
    research = _deterministic_company_research(
        company_name=company_name,
        source=source_hint,
    )
    return JobContext(
        input_url="",
        normalized_url="",
        source=source_hint,
        role_hint=role_hint,
        company_name=company_name,
        job_id="",
        fetch_status="provided_text",
        page_title="",
        description_excerpt=_truncate_excerpt(text),
        notes=(),
        company_research=research,
    )


def _normalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            parsed.query,
            "",
        )
    )


def _validate_job_url(url: str) -> None:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("job URL must use http or https scheme")
    if not parsed.netloc.strip():
        raise ValueError("job URL must include a hostname")
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise ValueError("job URL must include a hostname")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise ValueError("job URL host cannot target localhost")

    # Strip IPv6 brackets and zone identifiers (e.g. fe80::1%eth0) before parsing.
    host_for_ip_check = hostname.strip("[]").split("%", maxsplit=1)[0]
    try:
        ip = ipaddress.ip_address(host_for_ip_check)
    except ValueError:
        for resolved_ip in _resolve_hostname_ips(host_for_ip_check):
            if _is_non_public_ip(resolved_ip):
                raise ValueError(
                    "job URL host cannot target non-public IP ranges"
                ) from None
        return

    # Block non-public address classes to reduce SSRF blast radius.
    if _is_non_public_ip(ip):
        raise ValueError("job URL host cannot target non-public IP ranges")


def _resolve_hostname_ips(
    hostname: str,
) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
    except OSError:
        # Non-strict mode: allow validation to continue if DNS resolution fails.
        return ()

    resolved: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for _family, _socktype, _proto, _canonname, sockaddr in addrinfo:
        if not sockaddr:
            continue
        candidate = str(sockaddr[0]).split("%", maxsplit=1)[0]
        try:
            resolved.append(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return tuple(resolved)


def _is_non_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _truncate_excerpt(text: str, *, limit: int = _MAX_DESCRIPTION_EXCERPT) -> str:
    return text[:limit]


# ATS (applicant tracking system) hosts where the URL path's first segment is
# the hiring company's slug. Example: https://job-boards.greenhouse.io/<slug>/jobs/123.
# Matched as suffix: domain or *.domain (so any subdomain counts).
_ATS_PATH_SLUG_DOMAINS: tuple[str, ...] = (
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "smartrecruiters.com",
    "jobvite.com",
)

# Path-slug ATS hosts that must be matched *exactly* (not by domain suffix).
# Workable's marketing / docs / help live at workable.com / www.workable.com /
# help.workable.com — we don't want to treat those as job-board URLs and
# pull the first path segment as a company slug. Only apply.workable.com
# follows the apply.workable.com/<company>/j/<id>/ pattern. The same hosts
# are used by _try_board_api_fetch for Workable's JSON board API; the alias
# below keeps the two purposes pinned to the same source so adding a host
# can't accidentally diverge between ATS parsing and board-API dispatch.
_ATS_PATH_SLUG_HOSTS: tuple[str, ...] = ("apply.workable.com",)
_WORKABLE_BOARD_HOSTS: tuple[str, ...] = _ATS_PATH_SLUG_HOSTS
# ATS hosts where the netloc subdomain is the hiring company's slug.
# Example: https://<slug>.bamboohr.com/jobs/view.php?id=...
_ATS_SUBDOMAIN_DOMAINS: tuple[str, ...] = (
    "myworkdayjobs.com",
    "workdayjobs.com",
    "bamboohr.com",
    "breezy.hr",
    "recruitee.com",
    "personio.com",
    "teamtailor.com",
)

# Generic recruiting subdomain labels that we should walk past when falling
# back to URL-derived company extraction. Without this, a hostname like
# careers.westernunion.com yields "Careers" as the company, masking the
# real brand sitting one label deeper.
_GENERIC_RECRUITING_SUBDOMAINS: frozenset[str] = frozenset(
    {
        "www",
        "careers",
        "career",
        "jobs",
        "apply",
        "recruiting",
        "recruitment",
        "hire",
        "hiring",
        "talent",
        "people",
        "boards",
    }
)

# Page titles that the static fetcher gets stuck on when the JD body is
# JS-rendered: the shell HTML's <title> is just navigation boilerplate,
# not a real role. Rejecting these keeps URL/path-based role extraction
# from being shadowed by a meaningless title.
_GENERIC_PAGE_TITLES: frozenset[str] = frozenset(
    {
        "careers",
        "career",
        "jobs",
        "job listings",
        "career opportunities",
        "join our team",
        "open positions",
        "open roles",
        "current openings",
    }
)

# Single-word level / seniority / work-arrangement values that show up as
# search-filter query strings on hosted ATS pages (e.g. Workday's `?q=staff`
# is a level filter, not the role). Rejecting these as role values lets
# _extract_role_hint fall through to the URL path slug, which usually
# carries the actual role title. Multi-token query values are still
# accepted — `?keywords=Senior Software Engineer` is the real role even
# though "Senior" is in this set.
_GENERIC_ROLE_LEVEL_FILTERS: frozenset[str] = frozenset(
    {
        # Levels / seniority
        "staff",
        "senior",
        "principal",
        "junior",
        "intern",
        "lead",
        "director",
        "vp",
        "manager",
        # Generic role nouns (when they appear alone, they're filters, not roles)
        "engineer",
        "developer",
        "engineering",
        "software",
        # Work arrangement
        "remote",
        "hybrid",
        "onsite",
        "fulltime",
        "parttime",
        "contract",
    }
)


def _infer_source(netloc: str) -> str:
    host = netloc.lower().split(":", maxsplit=1)[0]  # strip optional port
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return "linkedin"
    if host == "indeed.com" or host.endswith(".indeed.com"):
        return "indeed"
    if host in _ATS_PATH_SLUG_HOSTS:
        return "ats"
    for domain in _ATS_PATH_SLUG_DOMAINS + _ATS_SUBDOMAIN_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return "ats"
    if host:
        return "company-site"
    return "unknown"


def _extract_ats_company_slug(host: str, path: str) -> str:
    """Extract the hiring company slug from a known ATS URL.

    Returns an empty string if the URL doesn't match any known ATS host or if
    the slug position is empty. Slugs are returned verbatim from the URL (no
    word-splitting); callers can humanize via `.title()` or hand off to the
    LLM for further refinement.
    """
    host = host.lower().split(":", maxsplit=1)[0]
    if not host:
        return ""

    if host in _ATS_PATH_SLUG_HOSTS:
        segments = [seg for seg in path.split("/") if seg.strip()]
        return segments[0] if segments else ""

    for domain in _ATS_PATH_SLUG_DOMAINS:
        if host == domain or host.endswith("." + domain):
            segments = [seg for seg in path.split("/") if seg.strip()]
            return segments[0] if segments else ""

    for domain in _ATS_SUBDOMAIN_DOMAINS:
        if host.endswith("." + domain):
            sub = host[: -(len(domain) + 1)]
            labels = [label for label in sub.split(".") if label]
            if labels and labels[0] != "www":
                return labels[0]
            if len(labels) >= 2:
                return labels[1]
    return ""


def _extract_job_id(query: dict[str, list[str]], path: str) -> str:
    keys = ("currentJobId", "jk", "jobId", "job_id")
    for key in keys:
        values = query.get(key, [])
        if values and values[0].strip():
            return values[0].strip()

    path_segments = [segment for segment in path.split("/") if segment]
    numeric_segments = [segment for segment in path_segments if segment.isdigit()]
    if numeric_segments:
        return numeric_segments[-1]
    return ""


def _extract_role_hint(
    *,
    query: dict[str, list[str]],
    path: str,
    source: str,
    page_title: str,
    description: str,
) -> str:
    role_from_title = _extract_role_from_title(source=source, title=page_title)
    if role_from_title:
        return role_from_title

    role_keys = ("keywords", "q", "title", "position")
    for key in role_keys:
        values = query.get(key, [])
        if not (values and values[0].strip()):
            continue
        candidate = values[0].strip()
        # Single-word level / arrangement filters (e.g. ?q=staff on Workday) are
        # search filters, not roles. Skip and fall through to path/description
        # extraction, which usually has the real role slug.
        if (
            len(candidate.split()) == 1
            and candidate.lower() in _GENERIC_ROLE_LEVEL_FILTERS
        ):
            continue
        return candidate

    role_from_path = _extract_role_from_path(path=path)
    if role_from_path:
        return role_from_path

    return _extract_role_from_description(description)


def _extract_company_name(
    *,
    source: str,
    netloc: str,
    path: str = "",
    page_title: str,
    description: str,
) -> str:
    title = page_title.strip()
    if source == "linkedin" and title:
        raw = title.split("|")[0]
        segments = [segment.strip() for segment in raw.split(" - ") if segment.strip()]
        if len(segments) >= 2:
            return segments[1]

    if source == "indeed" and title:
        raw = title.split("|")[0]
        segments = [segment.strip() for segment in raw.split(" - ") if segment.strip()]
        if len(segments) >= 3:
            return segments[2]

    if source == "ats":
        ats_slug = _extract_ats_company_slug(netloc, path)
        if ats_slug:
            return ats_slug

    marker = " at "
    lower = description.lower()
    if marker in lower:
        start = lower.index(marker) + len(marker)
        candidate = description[start:].split(".")[0].strip()
        if candidate:
            return candidate

    if source == "company-site":
        hostname = netloc.split(":", maxsplit=1)[0].strip().lower()
        labels = [label for label in hostname.split(".") if label]
        # Strip leading generic recruiting subdomains (www, careers, jobs,
        # apply, etc.) so e.g. careers.westernunion.com -> "westernunion"
        # rather than "Careers". Walks the chain in case of multiple
        # stacked generics like apply.careers.example.com. The
        # ``len(labels) > 2`` guard stops once only two labels remain so we
        # don't collapse past the brand label on apex hostnames like
        # jobs.com or careers.com (which would otherwise leave just the
        # TLD and produce 'Com' as the company). Note: this is a label-
        # count heuristic, not a public-suffix-list lookup — multi-part
        # suffixes such as co.uk are not specifically handled, but the
        # guard is sufficient for the apex-domain failure mode it targets.
        while len(labels) > 2 and labels[0] in _GENERIC_RECRUITING_SUBDOMAINS:
            labels = labels[1:]
        host_label = labels[0] if labels else ""
        # Companies that bake "jobs" / "careers" into their host name
        # (e.g. amazonjobs.com): strip the suffix to recover the brand.
        for suffix in ("jobs", "careers", "career"):
            if host_label.endswith(suffix) and len(host_label) > len(suffix):
                host_label = host_label[: -len(suffix)]
                break
        return host_label.upper() if host_label in {"hp", "ibm"} else host_label.title()

    return ""


def _extract_role_from_title(*, source: str, title: str) -> str:
    if not title.strip():
        return ""
    cleaned = title.split("|")[0].strip()
    # When the static fetch only saw the navigation shell (typical on
    # JS-rendered job boards), the title is often a generic recruiting
    # boilerplate string. Treat those as no-signal so the caller falls
    # through to URL/path/description-based role extraction instead.
    if cleaned.lower() in _GENERIC_PAGE_TITLES:
        return ""
    if source in {"linkedin", "indeed", "company-site", "ats"} and " - " in cleaned:
        lhs = cleaned.split(" - ")[0].strip()
        # Same generic-title guard after splitting: 'Careers - Acme Corp'
        # should fall through, not return 'Careers' as the role.
        if lhs.lower() in _GENERIC_PAGE_TITLES:
            return ""
        return lhs
    return ""


def _extract_role_from_description(description: str) -> str:
    text = description.strip()
    if not text:
        return ""
    lowered = text.lower()
    token = "looking for a "
    if token in lowered:
        start = lowered.index(token) + len(token)
        return text[start:].split(".")[0].strip()
    return ""


def _extract_role_from_path(*, path: str) -> str:
    segments = [segment for segment in path.split("/") if segment.strip()]
    ignored = {"job", "jobs", "careers", "career", "position", "opening"}
    candidates: list[str] = []
    for segment in segments:
        lowered = segment.lower()
        if lowered in ignored:
            continue
        if lowered.isdigit():
            continue
        if "-" not in segment:
            continue
        if not any(char.isalpha() for char in segment):
            continue
        candidates.append(segment)

    if not candidates:
        return ""
    return _humanize_role_slug(candidates[-1])


def _humanize_role_slug(slug: str) -> str:
    acronyms = {"sdet", "qa", "sre", "ml", "ai", "api", "ui", "ux", "sql"}
    tokens = [token for token in slug.split("-") if token]
    normalized: list[str] = []
    for token in tokens:
        lowered = token.lower()
        if lowered in acronyms:
            normalized.append(lowered.upper())
        else:
            normalized.append(token.capitalize())
    return " ".join(normalized).strip()


def _extract_role_from_text_blob(text: str) -> str:
    if not text:
        return ""
    patterns = (
        r"(?im)^\s*(?:job\s*title|title|position|role)\s*:\s*(.+?)\s*$",
        r"(?is)\b(?:seeking|looking\s+for)\s+(?:an?\s+)?(.+?)(?:\.|\n|,)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return " ".join(match.group(1).split())
    return ""


def _extract_company_from_text_blob(text: str) -> str:
    if not text:
        return ""
    patterns = (
        r"(?im)^\s*(?:company|employer|organization)\s*:\s*(.+?)\s*$",
        r"(?is)\bjoin\s+(.+?)(?:\.|\n|,)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return " ".join(match.group(1).split())
    return ""


# Tags whose inner text content is page-rendering machinery, never JD
# prose: their contents are CSS rules, JS source code, or fallback
# markup that the user-visible browser hides. Skipping them prevents
# the LLM-tailoring stage from being drowned in inline-stylesheet
# noise on JS-rendered pages (issue #293). Tracked via a per-tag
# counter so technically-malformed nested cases (rare but defensive)
# still bottom out correctly.
#
# Exception: `<script type="application/ld+json">` blocks carry
# structured JSON-LD job-schema data (the primary JD source on Workday
# and many other JS-rendered boards). Those are kept — see
# `_is_kept_script` below.
_NON_PROSE_TAGS: frozenset[str] = frozenset({"style", "script", "noscript"})

# Script `type` attribute values whose payload is JD-relevant data,
# NOT runnable JavaScript. Compared case-insensitively. Currently
# limited to JSON-LD (RFC 7159 / schema.org) since that's the format
# Workday and most structured-data-emitting boards use; extend
# conservatively (e.g. `application/json`) only if a real consumer
# needs it.
_KEPT_SCRIPT_TYPES: frozenset[str] = frozenset({"application/ld+json"})


def _is_kept_script(attrs: list[tuple[str, str | None]]) -> bool:
    """True when a `<script>` element should be treated as data, not code.

    Inspects the `type` attribute (case-insensitive). Returns False for
    the no-attribute case (default `text/javascript`) and any attr
    value not in `_KEPT_SCRIPT_TYPES`.
    """
    for key, value in attrs:
        if (
            key.lower() == "type"
            and (value or "").strip().lower() in _KEPT_SCRIPT_TYPES
        ):
            return True
    return False


class _PlainTextHTMLParser(HTMLParser):
    """Strip HTML tags, collect plain text. Used to render API-returned
    HTML (Greenhouse \"content\", Workable \"description\") and
    Playwright-rendered pages into the plain-text shape the rest of
    the pipeline expects.

    Drops the contents of `<style>`, `<script>` (except JSON-LD), and
    `<noscript>` blocks entirely — these are never JD prose and their
    inline content (CSS rules, JS source) blew up the description
    excerpt on JS-rendered pages. See #293. JSON-LD scripts are kept
    because Workday and other structured-data boards embed the JD body
    there.
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        # Per-tag depth counter; non-zero ⇒ skip data emission.
        self._skip_depth: dict[str, int] = {tag: 0 for tag in _NON_PROSE_TAGS}

    def _in_skip_block(self) -> bool:
        return any(depth > 0 for depth in self._skip_depth.values())

    def handle_data(self, data: str) -> None:
        if self._in_skip_block():
            return
        self._chunks.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in _NON_PROSE_TAGS:
            # JSON-LD scripts carry structured JD data — keep them.
            if lower == "script" and _is_kept_script(attrs):
                return
            self._skip_depth[lower] += 1
            return
        if lower in {"br", "p", "li", "div", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in _NON_PROSE_TAGS and self._skip_depth[lower] > 0:
            self._skip_depth[lower] -= 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Route self-closing tags (e.g. <br/>, <br />) through the same
        # break-inserting logic as their open-tag form. Without this,
        # XHTML-style line breaks would be silently dropped, concatenating
        # text that should land on separate lines. Self-closing
        # script/style/noscript are technically invalid HTML5 but harmless
        # here — they'd carry no content to skip.
        if tag.lower() in _NON_PROSE_TAGS:
            return
        self.handle_starttag(tag, attrs)

    @property
    def text(self) -> str:
        return _html_lib.unescape("".join(self._chunks)).strip()


def _html_to_text(raw: str) -> str:
    """Convert API-returned HTML into normalized plain text."""
    if not raw:
        return ""
    parser = _PlainTextHTMLParser()
    parser.feed(raw)
    parser.close()
    # Collapse runs of whitespace (excluding newlines we inserted) so the
    # downstream description-excerpt truncation gets useful content. NBSP
    # (\xa0) is included because HTMLParser preserves the NBSP character
    # when &nbsp; is decoded; runs of NBSP would otherwise leave odd
    # spacing in the extracted JD body.
    text = re.sub(r"[ \t\xa0]+", " ", parser.text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _fetch_json_api(api_url: str) -> dict[str, Any] | None:
    """HTTP GET + JSON parse with the same security validation as page fetch.

    Returns None on any failure so the caller can fall back to the
    static HTML fetch path.
    """
    try:
        _validate_job_url(_normalize_url(api_url))
    except Exception:  # noqa: BLE001
        return None
    request = Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": _FETCH_USER_AGENT},
    )
    opener = build_opener(_ValidatingRedirectHandler())
    try:
        with opener.open(request, timeout=8) as response:  # nosec B310 - validated above
            _validate_job_url(_normalize_url(response.geturl()))
            content_length_header = response.headers.get("Content-Length")
            if content_length_header:
                try:
                    if int(content_length_header) > _MAX_FETCH_BYTES:
                        return None
                except ValueError:
                    pass
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read(_MAX_FETCH_BYTES + 1)
            if len(content) > _MAX_FETCH_BYTES:
                return None
            text = content.decode(charset, errors="replace")
    except Exception:  # noqa: BLE001
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _fetch_greenhouse_via_api(*, board: str, job_id: str) -> FetchedPage | None:
    """Greenhouse public board API: returns full JD body as HTML in `content`."""
    if not (board and job_id):
        return None
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
    payload = _fetch_json_api(api_url)
    if payload is None:
        return None
    title = (payload.get("title") or "").strip()
    description = _html_to_text(payload.get("content") or "")
    # Require a non-empty description specifically (not just title-or-description):
    # downstream JD-term extraction and the LLM-tailoring stages all depend on
    # the description body. A title-only payload would short-circuit the
    # static-HTML fallback while still leaving description_excerpt empty,
    # defeating the whole point of the API path.
    if not description:
        return None
    return FetchedPage(
        status="fetched",
        title=title,
        description=description,
        notes=("source:greenhouse_api",),
    )


def _fetch_workable_via_api(*, account: str, shortcode: str) -> FetchedPage | None:
    """Workable widget API: returns full JD body as HTML in `description`."""
    if not (account and shortcode):
        return None
    api_url = (
        f"https://apply.workable.com/api/v3/widget/accounts/{account}/jobs/{shortcode}"
    )
    payload = _fetch_json_api(api_url)
    if payload is None:
        return None
    title = (payload.get("title") or "").strip()
    description = _html_to_text(payload.get("description") or "")
    # Same rationale as the Greenhouse path: require a non-empty description
    # so a title-only payload doesn't suppress the static-HTML fallback.
    if not description:
        return None
    return FetchedPage(
        status="fetched",
        title=title,
        description=description,
        notes=("source:workable_api",),
    )


def _try_board_api_fetch(url: str) -> FetchedPage | None:
    """Detect supported job-board URL families and try their JSON APIs.

    Returns a FetchedPage on success, or None when the URL doesn't
    match a supported family or the API call fails. The static-HTML
    fetcher is the fallback in either case.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [s for s in parsed.path.split("/") if s]

    if host in _GREENHOUSE_BOARD_HOSTS:
        # boards.greenhouse.io/<board>/jobs/<job_id>
        if len(segments) >= 3 and segments[1] == "jobs":
            return _fetch_greenhouse_via_api(board=segments[0], job_id=segments[2])
    if host in _WORKABLE_BOARD_HOSTS:
        # apply.workable.com/<account>/j/<shortcode>/
        if len(segments) >= 3 and segments[1] == "j":
            return _fetch_workable_via_api(account=segments[0], shortcode=segments[2])
    return None


def _import_sync_playwright() -> Any:
    """Import playwright.sync_api lazily; return ``sync_playwright`` or None.

    Indirection makes the dependency a runtime concern rather than an
    import-time hard dep: the module loads cleanly without playwright
    installed, and only the Playwright code path needs it. Tests
    monkeypatch this helper to inject a fake sync_playwright.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415

        return sync_playwright
    except ImportError:
        return None


def _playwright_enabled() -> bool:
    """True when the user opted into the Playwright path AND it's available."""
    if os.getenv(_PLAYWRIGHT_ENABLED_ENV, "0").strip() != "1":
        return False
    return _import_sync_playwright() is not None


def _host_needs_javascript_render(host: str) -> bool:
    """Match host against the JS-rendered allowlist.

    Returns True when the host is in either _JS_RENDERED_EXACT_HOSTS
    (exact match) or under one of _JS_RENDERED_HOST_FAMILIES (suffix
    match — e.g. ``becu.wd1.myworkdayjobs.com`` matches
    ``myworkdayjobs.com``).
    """
    host = (host or "").lower().split(":", maxsplit=1)[0]
    if not host:
        return False
    if host in _JS_RENDERED_EXACT_HOSTS:
        return True
    return any(
        host == family or host.endswith("." + family)
        for family in _JS_RENDERED_HOST_FAMILIES
    )


def _should_use_playwright(url: str, static_result: FetchedPage) -> bool:
    """Decide whether to retry a fetch via the Playwright path.

    Two triggers:
    - host is in the curated JS-rendered allowlist (always retry); or
    - the static fetch came back below _PLAYWRIGHT_RETRY_THRESHOLD_CHARS
      of description content (catches JS-rendered domains we haven't
      curated yet).

    Both paths require the env-var opt-in via ``_playwright_enabled()``;
    callers that haven't enabled the Playwright path never invoke this.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if _host_needs_javascript_render(host):
        return True
    return len(static_result.description or "") < _PLAYWRIGHT_RETRY_THRESHOLD_CHARS


def _playwright_fetch_html(sync_pw: Any, url: str) -> tuple[str, str] | None:
    """Inner orchestration: launch Chromium, navigate, return (title, html).

    Separated from the public _fetch_via_playwright wrapper so the
    browser-dance logic can be tested without exercising the wrapper's
    URL validation + result construction. ``sync_pw`` is the
    ``playwright.sync_api.sync_playwright`` callable, injected so tests
    can substitute a fake.
    """
    try:
        with sync_pw() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=_FETCH_USER_AGENT)
                page.goto(
                    url,
                    timeout=int(_PLAYWRIGHT_TIMEOUT_SECONDS * 1000),
                    wait_until="domcontentloaded",
                )
                # Late-firing JS settle window. Most JD boards finish
                # rendering within ~1 s of domcontentloaded.
                page.wait_for_timeout(_PLAYWRIGHT_SETTLE_MS)
                title = page.title() or ""
                content_html = page.content() or ""
                if len(content_html) > _MAX_FETCH_BYTES:
                    content_html = content_html[:_MAX_FETCH_BYTES]
                return title, content_html
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Playwright fetch failed for %s: %s", url, exc, exc_info=True)
        return None


def _fetch_via_playwright(url: str) -> FetchedPage | None:
    """Fetch JD body via headless Chromium for JS-rendered pages.

    Public wrapper. Returns None when:
    - playwright isn't installed (caller falls back to static result);
    - the URL fails security validation;
    - the browser dance fails (timeout, launch error, etc.);
    - the rendered content is empty after _html_to_text.

    No raised exceptions; all failures degrade to None so the caller
    can keep the static result.
    """
    sync_pw = _import_sync_playwright()
    if sync_pw is None:
        return None
    try:
        _validate_job_url(_normalize_url(url))
    except Exception:  # noqa: BLE001
        return None

    raw = _playwright_fetch_html(sync_pw, url)
    if raw is None:
        return None
    title, content_html = raw
    description = _html_to_text(content_html)
    if not description.strip():
        return None
    return FetchedPage(
        status="fetched",
        title=title,
        description=description,
        notes=("source:playwright",),
    )


def _fetch_static_job_page_metadata(url: str) -> FetchedPage:
    """Static (urllib) fetch of a JD page.

    Always returns a FetchedPage and never raises — every failure mode
    (Content-Length too large, response body too large, urllib raises
    during open/read) is encoded as ``status="fetch_failed"`` with a
    structured ``notes`` tag (e.g. ``"fetch_failed:ResponseTooLarge"``,
    ``"fetch_failed:URLError"``).

    The orchestration layer (``_fetch_job_page_metadata``) inspects the
    returned status / description / host to decide whether to invoke
    the Playwright fallthrough — so even when this function returns a
    fetch_failed result, JS-rendered hosts on the allowlist still get
    Playwright tried.
    """
    request = Request(url, headers={"User-Agent": _FETCH_USER_AGENT})
    opener = build_opener(_ValidatingRedirectHandler())
    try:
        # Re-validate immediately before connect to reduce DNS rebinding window.
        _validate_job_url(_normalize_url(url))
        with opener.open(request, timeout=8) as response:  # nosec B310 - user-supplied URL
            _validate_job_url(_normalize_url(response.geturl()))
            content_length_header = response.headers.get("Content-Length")
            if content_length_header:
                try:
                    if int(content_length_header) > _MAX_FETCH_BYTES:
                        return FetchedPage(
                            status="fetch_failed",
                            title="",
                            description="",
                            notes=("fetch_failed:ContentTooLarge",),
                        )
                except ValueError:
                    # Ignore malformed Content-Length and continue with bounded read.
                    pass
            charset = response.headers.get_content_charset() or "utf-8"
            content = response.read(_MAX_FETCH_BYTES + 1)
            if len(content) > _MAX_FETCH_BYTES:
                return FetchedPage(
                    status="fetch_failed",
                    title="",
                    description="",
                    notes=("fetch_failed:ResponseTooLarge",),
                )
            html_text = content.decode(charset, errors="replace")
    except Exception as exc:  # noqa: BLE001
        return FetchedPage(
            status="fetch_failed",
            title="",
            description="",
            notes=(f"fetch_failed:{exc.__class__.__name__}",),
        )
    parser = _MetadataParser()
    parser.feed(html_text)
    parser.close()
    return FetchedPage(
        status="fetched",
        title=parser.title,
        description=parser.description,
        notes=(),
    )


def _fetch_job_page_metadata(url: str) -> FetchedPage:
    fixture_path = os.getenv(_JOB_PAGE_FIXTURE_ENV, "").strip()
    if fixture_path:
        return _fetch_job_page_metadata_from_fixture(Path(fixture_path))
    api_result = _try_board_api_fetch(url)
    if api_result is not None:
        return api_result
    static_result = _fetch_static_job_page_metadata(url)
    # JS-rendered fallback: when the user has opted into Playwright AND
    # either the host is in our curated allowlist or the static fetch
    # came back near-empty (including outright `fetch_failed`), retry
    # via headless Chromium and prefer that result if it produced
    # non-empty content. Static result still wins on any Playwright
    # failure. Issue #281: prior implementation early-returned on
    # static-fetch failures (ResponseTooLarge / ContentTooLarge / read
    # exceptions) without trying Playwright, even for allowlisted JS-
    # rendered hosts where Playwright is the only viable path.
    if _playwright_enabled() and _should_use_playwright(url, static_result):
        pw_result = _fetch_via_playwright(url)
        if pw_result is not None and pw_result.description.strip():
            return pw_result
    return static_result


def _fetch_job_page_metadata_from_fixture(path: Path) -> FetchedPage:
    assert_not_blocked_runtime_input(path)
    resolved_path = path.resolve()
    try:
        html_text = resolved_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return FetchedPage(
            status="fetch_failed",
            title="",
            description="",
            notes=(f"fixture_read_failed:{exc.__class__.__name__}",),
        )

    parser = _MetadataParser()
    parser.feed(html_text)
    parser.close()
    return FetchedPage(
        status="fetched",
        title=parser.title,
        description=parser.description,
        notes=(f"fixture:{resolved_path.name}",),
    )


def _deterministic_company_research(
    *, company_name: str, source: str
) -> CompanyResearch | None:
    if not company_name.strip():
        return None

    normalized = company_name.strip().lower()
    known_profiles = {
        "linkedin": (
            "Professional networking and recruiting technology",
            "Talent, hiring workflows, and job distribution platform",
        ),
        "indeed": (
            "Employment marketplace and recruiting technology",
            "Job discovery, employer branding, and applicant workflows",
        ),
        "hp": (
            "Enterprise and consumer computing hardware/software",
            "Endpoint devices, collaboration systems, and enterprise IT tooling",
        ),
        "poly": (
            "Unified communications and collaboration hardware",
            "Video/audio collaboration endpoints and meeting-room ecosystem",
        ),
        "polycom": (
            "Unified communications and collaboration hardware",
            "Video/audio collaboration endpoints and meeting-room ecosystem",
        ),
    }

    for key, hints in known_profiles.items():
        if key in normalized:
            return CompanyResearch(
                company_name=company_name,
                industry_hint=hints[0],
                product_hint=hints[1],
                strategy="deterministic-v1",
                confidence="medium",
            )

    default_product_hint = (
        "Public listing signals only; richer enrichment is deferred to provider-backed "
        "research in later phases"
    )
    if source == "linkedin":
        default_product_hint = (
            "LinkedIn listing signals captured; full company enrichment deferred to "
            "future provider adapters"
        )
    elif source == "indeed":
        default_product_hint = (
            "Indeed listing signals captured; full company enrichment deferred to "
            "future provider adapters"
        )

    return CompanyResearch(
        company_name=company_name,
        industry_hint="Industry unknown (deterministic baseline)",
        product_hint=default_product_hint,
        strategy="deterministic-v1",
        confidence="low",
    )
