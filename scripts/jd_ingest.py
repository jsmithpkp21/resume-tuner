#!/usr/bin/env python3
"""Deterministic job-input ingestion for resume tailoring.

This module intentionally keeps behavior predictable for MVP:
- accept a job posting URL and parse stable hints from URL/query/title
- attempt lightweight page metadata fetch with graceful fallback
- produce low-risk deterministic company context scaffolding

Future phases can replace or augment this with richer provider adapters.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse, urlunparse
from urllib.request import Request, urlopen


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
        description_excerpt=fetched.description,
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
        description_excerpt=text[:500],
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


def _infer_source(netloc: str) -> str:
    host = netloc.lower()
    if "linkedin.com" in host:
        return "linkedin"
    if "indeed.com" in host:
        return "indeed"
    if host:
        return "company-site"
    return "unknown"


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
        if values and values[0].strip():
            return values[0].strip()

    role_from_path = _extract_role_from_path(path=path)
    if role_from_path:
        return role_from_path

    return _extract_role_from_description(description)


def _extract_company_name(
    *, source: str, netloc: str, page_title: str, description: str
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
        if labels and labels[0] == "www":
            labels = labels[1:]
        host_label = labels[0] if labels else ""
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
    if source in {"linkedin", "indeed", "company-site"} and " - " in cleaned:
        return cleaned.split(" - ")[0].strip()
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


def _fetch_job_page_metadata(url: str) -> FetchedPage:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=8) as response:  # nosec B310 - user-supplied URL
            charset = response.headers.get_content_charset() or "utf-8"
            html_text = response.read().decode(charset, errors="replace")
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
