"""Targeted unit tests for scripts/jd_ingest.py URL-fallback behavior.

Covers the fixes from issue #247:

- Workable URLs (apply.workable.com/<company>/...) are recognized as
  ATS path-slug hosts so the company comes from the path, not the
  'apply' subdomain.
- company-site fallback walks past generic recruiting subdomains
  (careers., jobs., apply., etc.) before falling back to the leading
  hostname label.
- Generic page titles (Careers, Jobs, ...) are rejected by
  _extract_role_from_title so the caller falls through to URL/path
  extraction instead of using navigation-shell boilerplate as the role.
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.jd_ingest import (
    FetchedPage,
    _extract_company_name,
    _extract_role_from_title,
    _extract_role_hint,
    _fetch_greenhouse_via_api,
    _fetch_json_api,
    _fetch_via_playwright,
    _fetch_workable_via_api,
    _host_needs_javascript_render,
    _html_to_text,
    _infer_source,
    _playwright_enabled,
    _playwright_fetch_html,
    _should_use_playwright,
    _try_board_api_fetch,
)

# --- _extract_company_name: ATS path-slug for Workable -------------------


def test_workable_apply_subdomain_uses_path_slug_for_company() -> None:
    """apply.workable.com/<company>/j/<id>/ -> company from path segment.

    Pre-fix this returned 'Apply' from the leading hostname label.
    """
    name = _extract_company_name(
        source="ats",
        netloc="apply.workable.com",
        path="/murmuration/j/44B92237B8/",
        page_title="",
        description="",
    )
    assert name == "murmuration"


def test_workable_apply_subdomain_classifies_as_ats() -> None:
    """apply.workable.com is an ATS host (path-slug pattern)."""
    assert _infer_source("apply.workable.com") == "ats"


@pytest.mark.parametrize(
    "netloc",
    [
        # Round-2 review on PR #249: only apply.workable.com is the JD-board
        # surface; the apex / marketing / docs / help domains must not be
        # classified as ATS, otherwise _extract_ats_company_slug would take
        # the first path segment as the "company" on a non-job page.
        "workable.com",
        "www.workable.com",
        "help.workable.com",
        "support.workable.com",
        "docs.workable.com",
    ],
)
def test_non_apply_workable_hostnames_are_not_ats(netloc: str) -> None:
    """Marketing / docs / help workable.com hosts are not ATS job boards."""
    assert _infer_source(netloc) != "ats"


# --- _extract_company_name: generic-subdomain skipping -------------------


@pytest.mark.parametrize(
    "netloc, expected",
    [
        # Single generic prefix (the case that bit job4_westernunion).
        ("careers.westernunion.com", "Westernunion"),
        ("jobs.example.com", "Example"),
        ("apply.example.com", "Example"),
        ("recruiting.example.com", "Example"),
        ("hire.example.com", "Example"),
        ("talent.example.com", "Example"),
        ("boards.example.com", "Example"),
        # Multiple stacked generics walk through both.
        ("apply.careers.example.com", "Example"),
        # www stays handled (regression check on prior behavior).
        ("www.example.com", "Example"),
        ("www.careers.example.com", "Example"),
    ],
)
def test_company_site_skips_generic_recruiting_subdomains(
    netloc: str, expected: str
) -> None:
    name = _extract_company_name(
        source="company-site",
        netloc=netloc,
        path="/",
        page_title="",
        description="",
    )
    assert name == expected


@pytest.mark.parametrize(
    "netloc, expected",
    [
        # Apex hostname where the leading label happens to match a generic.
        # Without the registrable-domain guard, the strip loop would
        # collapse these to just the TLD ("Com"). With the guard we keep
        # the brand intact, even if the brand IS the generic word.
        ("jobs.com", "Jobs"),
        ("careers.com", "Careers"),
        ("people.com", "People"),
        ("hire.com", "Hire"),
    ],
)
def test_company_site_does_not_strip_past_registrable_domain(
    netloc: str, expected: str
) -> None:
    """Copilot review on PR #249: don't strip the registrable label.

    For a hostname like ``jobs.com`` the only label before the TLD is
    ``jobs``; stripping it would produce ``Com`` as the company name.
    """
    name = _extract_company_name(
        source="company-site",
        netloc=netloc,
        path="/",
        page_title="",
        description="",
    )
    assert name == expected


def test_company_site_strips_baked_in_jobs_suffix_after_generic_skip() -> None:
    """The 'amazonjobs.com -> Amazon' suffix-strip still fires.

    Confirms the new generic-subdomain skip didn't break the existing
    suffix-strip pass that handles companies which bake "jobs" or
    "careers" into their host name.
    """
    name = _extract_company_name(
        source="company-site",
        netloc="amazonjobs.com",
        path="/",
        page_title="",
        description="",
    )
    assert name == "Amazon"


# --- _extract_role_from_title: generic title rejection -------------------


@pytest.mark.parametrize(
    "title",
    [
        "Careers",
        "careers",
        "  Careers  ",
        "Jobs",
        "Career Opportunities",
        "Open Positions",
        "Open Roles",
        "Current Openings",
        "Join Our Team",
        "Job Listings",
    ],
)
def test_extract_role_from_title_rejects_generic_navigation_titles(
    title: str,
) -> None:
    """A title that's just recruiting boilerplate must not be used as a role.

    Before this fix, a JS-rendered page where the static fetcher only
    saw '<title>Careers</title>' produced 'Careers' as the role hint,
    polluting downstream tailoring.
    """
    assert _extract_role_from_title(source="company-site", title=title) == ""


def test_extract_role_from_title_keeps_real_role_with_separator() -> None:
    """Real titles with the canonical 'Role - Company' shape still parse."""
    assert (
        _extract_role_from_title(
            source="company-site",
            title="Staff Software Engineer - Acme Corp",
        )
        == "Staff Software Engineer"
    )


@pytest.mark.parametrize(
    "title",
    [
        "Careers - Acme Corp",
        "Jobs - Acme Corp",
        "Open Positions - Acme Corp",
        "  careers  -  Acme Corp",
    ],
)
def test_extract_role_from_title_rejects_generic_lhs_after_split(
    title: str,
) -> None:
    """Round-2 review on PR #249: generic LHS of the ' - ' split is rejected.

    Before this fix, 'Careers - Acme Corp' returned 'Careers' as the role
    because the generic-title check only ran on the un-split string.
    """
    assert _extract_role_from_title(source="company-site", title=title) == ""


# --- Issue #255 sub-item 1: ATS sources should also use title-based role ---


@pytest.mark.parametrize(
    "title, expected",
    [
        # Workable URLs (apply.workable.com/<co>/j/<id>/) are now classified
        # as ATS but the static fetcher still sees a useful <title>. Pre-fix
        # ATS sources returned "" from this function regardless.
        ("Staff SDET - Murmuration", "Staff SDET"),
        ("Senior Software Engineer - Acme Corp", "Senior Software Engineer"),
        ("Engineering Manager - Some Company | Workable", "Engineering Manager"),
    ],
)
def test_extract_role_from_title_now_runs_for_ats_source(
    title: str, expected: str
) -> None:
    """Issue #255 sub-item 1: ATS title extraction.

    Pre-fix the function only honored linkedin / indeed / company-site
    sources; ATS classification (Workable, Greenhouse, Lever, Workday)
    suppressed title-based role extraction even when the title carried
    the role.
    """
    assert _extract_role_from_title(source="ats", title=title) == expected


@pytest.mark.parametrize(
    "title",
    [
        # Workday's static-fetch shell title is typically generic boilerplate.
        # The post-split generic-title guard must still reject these even
        # under the now-eligible ATS source.
        "Career Opportunities",
        "Job Listings",
        "Open Positions",
        "Careers - Acme Corp",
    ],
)
def test_extract_role_from_title_still_rejects_generic_for_ats_source(
    title: str,
) -> None:
    """Generic shell titles must still return '' even when source=ats.

    Without this regression check, broadening the source set could
    unintentionally let Workday's "Career Opportunities" title slip
    through as the role.
    """
    assert _extract_role_from_title(source="ats", title=title) == ""


# --- Issue #255 sub-item 2: filter-style ?q= values must not become roles ---


@pytest.mark.parametrize(
    "query, expected_returns",
    [
        # The case that bit job3_becu — Workday URL with ?q=staff (search
        # filter), with no other role signal in title or description.
        ({"q": ["staff"]}, ""),
        # Other common filter values that should be rejected as roles.
        ({"q": ["senior"]}, ""),
        ({"q": ["remote"]}, ""),
        ({"q": ["principal"]}, ""),
        ({"keywords": ["software"]}, ""),
        # Title-cased single-word filter is also a filter.
        ({"q": ["Staff"]}, ""),
        # Non-filter single-word values still flow through (e.g. an actual
        # role name in `position`).
        ({"position": ["SDET"]}, "SDET"),
    ],
)
def test_extract_role_hint_skips_single_word_filter_values(
    query: dict[str, list[str]], expected_returns: str
) -> None:
    """Issue #255 sub-item 2: ?q=staff is a filter, not a role.

    With no signal in title / path / description, role-from-query is the
    last resort. When the only query value is a single-word level/filter
    qualifier (`staff`, `senior`, `remote`, ...), reject it and let
    later branches return '' instead.
    """
    result = _extract_role_hint(
        query=query,
        path="/",
        source="ats",
        page_title="",
        description="",
    )
    assert result == expected_returns


def test_extract_role_hint_keeps_multi_word_filter_token_values() -> None:
    """Multi-token query values are accepted even if a token is filter-like.

    A real role like 'Senior Software Engineer' contains tokens that
    individually appear in the filter set; only single-token values are
    rejected.
    """
    result = _extract_role_hint(
        query={"keywords": ["Senior Software Engineer"]},
        path="/",
        source="ats",
        page_title="",
        description="",
    )
    assert result == "Senior Software Engineer"


def test_extract_role_hint_falls_through_to_path_when_query_is_filter() -> None:
    """When ?q=<filter> is rejected, path-slug extraction wins.

    This is the becu URL shape — single-word filter on top of a rich
    path slug. The filter must yield to the path so the actual role
    surfaces (even if humanization isn't perfect — that's separate work).
    """
    result = _extract_role_hint(
        query={"q": ["staff"]},
        path=(
            "/en-US/External/details/Staff-Software-Developer-Engineer-in-Test_R-13007"
        ),
        source="ats",
        page_title="",
        description="",
    )
    # The path-extraction humanization isn't perfect (trailing job-id is a
    # known wart, separate follow-up). Just confirm that the filter no
    # longer wins and a path-derived role is returned.
    assert result != "staff"
    assert "Staff" in result and "Software" in result and "Engineer" in result


# --- Issue #247 fix-3 (subset): board-API fetchers + dispatcher ----------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", ""),
        ("Plain text only", "Plain text only"),
        ("<p>Hello <b>world</b>!</p>", "Hello world!"),
        ("<p>One</p><p>Two</p>", "One\nTwo"),
        # HTML entities decode after tag-strip.
        ("<p>Smith &amp; Sons</p>", "Smith & Sons"),
        # NBSP is whitespace per str.isspace, so leading NBSP gets stripped.
        ("&nbsp; spaces", "spaces"),
        # NBSP runs (HTMLParser preserves the U+00A0 character when &nbsp;
        # decodes) are collapsed alongside ASCII spaces and tabs. Without
        # this, JD bodies that use &nbsp; for indentation produce
        # awkward-looking extracted text.
        ("<p>word&nbsp;&nbsp;&nbsp;word</p>", "word word"),
        ("<p>foo&nbsp; \tbar</p>", "foo bar"),
        # Adjacent block-open tags (div+p, div+p) leave a blank line between
        # paragraphs — fine for JD downstream truncation.
        ("<div><p>A</p></div><div><p>B</p></div>", "A\n\nB"),
        # Whitespace runs are normalized.
        ("<p>too    many    spaces</p>", "too many spaces"),
        # Self-closing line breaks (XHTML-style) must produce newlines just
        # like the open-tag form. PR #263 round-2 review caught that
        # HTMLParser routes <br/> / <br /> through handle_startendtag,
        # which the parser previously didn't override.
        ("Line 1<br/>Line 2", "Line 1\nLine 2"),
        ("Line 1<br />Line 2", "Line 1\nLine 2"),
        ("Line 1<BR/>Line 2", "Line 1\nLine 2"),
        # Self-closing block tags also break.
        ("Line 1<p/>Line 2", "Line 1\nLine 2"),
        # Multiple self-closing breaks in a row.
        ("a<br/>b<br/>c", "a\nb\nc"),
    ],
)
def test_html_to_text_normalizes(raw: str, expected: str) -> None:
    assert _html_to_text(raw) == expected


def test_try_board_api_fetch_dispatches_to_greenhouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_json(api_url: str) -> dict[str, str]:
        captured["api_url"] = api_url
        return {"title": "Senior SWE", "content": "<p>JD body here</p>"}

    monkeypatch.setattr("scripts.jd_ingest._fetch_json_api", fake_json)

    page = _try_board_api_fetch("https://boards.greenhouse.io/acme/jobs/12345")
    assert page is not None
    assert (
        captured["api_url"]
        == "https://boards-api.greenhouse.io/v1/boards/acme/jobs/12345"
    )
    assert page.title == "Senior SWE"
    assert "JD body here" in page.description
    assert "source:greenhouse_api" in page.notes


def test_try_board_api_fetch_dispatches_to_job_boards_greenhouse_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The newer job-boards.greenhouse.io subdomain dispatches the same."""
    captured: dict[str, str] = {}

    def fake_json(api_url: str) -> dict[str, str]:
        captured["api_url"] = api_url
        return {"title": "T", "content": "<p>D</p>"}

    monkeypatch.setattr("scripts.jd_ingest._fetch_json_api", fake_json)
    page = _try_board_api_fetch(
        "https://job-boards.greenhouse.io/elitetechnology/jobs/5206489008"
    )
    assert page is not None
    assert (
        captured["api_url"] == "https://boards-api.greenhouse.io/v1/boards/"
        "elitetechnology/jobs/5206489008"
    )


def test_try_board_api_fetch_dispatches_to_workable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_json(api_url: str) -> dict[str, str]:
        captured["api_url"] = api_url
        return {"title": "Staff SDET", "description": "<p>Workable JD body</p>"}

    monkeypatch.setattr("scripts.jd_ingest._fetch_json_api", fake_json)

    page = _try_board_api_fetch("https://apply.workable.com/murmuration/j/44B92237B8/")
    assert page is not None
    assert captured["api_url"] == (
        "https://apply.workable.com/api/v3/widget/accounts/murmuration/jobs/44B92237B8"
    )
    assert page.title == "Staff SDET"
    assert "Workable JD body" in page.description
    assert "source:workable_api" in page.notes


@pytest.mark.parametrize(
    "url",
    [
        # Non-supported hosts must not dispatch (caller falls back to HTML).
        "https://www.example.com/careers/123",
        "https://becu.wd1.myworkdayjobs.com/.../R-13007",
        "https://careers.westernunion.com/job-details/23275610/staff/",
        "https://www.linkedin.com/jobs/view/1234",
        # Greenhouse host but no /jobs/<id> tail.
        "https://boards.greenhouse.io/acme",
        "https://boards.greenhouse.io/acme/applications",
        # Workable host but no /j/<shortcode>.
        "https://apply.workable.com/acme/dashboard",
    ],
)
def test_try_board_api_fetch_returns_none_for_unsupported_urls(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """Unsupported URL families must not call the JSON API."""

    def fake_json(_api_url: str) -> dict[str, str]:
        raise AssertionError("API should not be called for non-matching URLs")

    monkeypatch.setattr("scripts.jd_ingest._fetch_json_api", fake_json)
    assert _try_board_api_fetch(url) is None


def test_try_board_api_fetch_returns_none_on_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the API itself fails, dispatch returns None for HTML fallback."""

    monkeypatch.setattr("scripts.jd_ingest._fetch_json_api", lambda _url: None)
    assert _try_board_api_fetch("https://boards.greenhouse.io/acme/jobs/12345") is None
    assert _try_board_api_fetch("https://apply.workable.com/acme/j/abc123/") is None


def test_fetch_greenhouse_via_api_returns_none_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An API call that returns an empty / title-less / content-less payload
    should be treated as a failure so the caller falls back to HTML."""
    monkeypatch.setattr(
        "scripts.jd_ingest._fetch_json_api",
        lambda _u: {"title": "", "content": ""},
    )
    assert _fetch_greenhouse_via_api(board="acme", job_id="123") is None


def test_fetch_workable_via_api_returns_none_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.jd_ingest._fetch_json_api",
        lambda _u: {"title": "", "description": ""},
    )
    assert _fetch_workable_via_api(account="acme", shortcode="abc") is None


def test_fetch_greenhouse_via_api_skips_when_required_url_parts_missing() -> None:
    """Defensive: empty board / job_id arguments shouldn't issue a request."""
    assert _fetch_greenhouse_via_api(board="", job_id="123") is None
    assert _fetch_greenhouse_via_api(board="acme", job_id="") is None


def test_fetch_workable_via_api_skips_when_required_url_parts_missing() -> None:
    assert _fetch_workable_via_api(account="", shortcode="abc") is None
    assert _fetch_workable_via_api(account="acme", shortcode="") is None


def test_fetch_greenhouse_via_api_returns_none_on_title_only_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #247 fix-3 review: title alone is not enough.

    Downstream JD-term extraction and LLM tailoring stages depend on
    description text. A title-only API payload would short-circuit
    the static-HTML fallback while leaving description_excerpt empty,
    defeating the whole point of the API path.
    """
    monkeypatch.setattr(
        "scripts.jd_ingest._fetch_json_api",
        lambda _u: {"title": "Senior SWE", "content": ""},
    )
    assert _fetch_greenhouse_via_api(board="acme", job_id="123") is None


def test_fetch_workable_via_api_returns_none_on_title_only_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rationale as the Greenhouse equivalent — require a description."""
    monkeypatch.setattr(
        "scripts.jd_ingest._fetch_json_api",
        lambda _u: {"title": "Staff SDET", "description": ""},
    )
    assert _fetch_workable_via_api(account="acme", shortcode="abc") is None


# --- Issue #247 fix-3 review: _fetch_json_api low-level coverage ---------


class _FakeResponse:
    """Minimal context-manager stand-in for urllib's response object."""

    def __init__(
        self,
        *,
        body: bytes,
        content_length: str | None = None,
        charset: str = "utf-8",
        url: str | None = None,
    ) -> None:
        self._body = body
        self._content_length = content_length
        self._charset = charset
        self._url = url

        class _Headers:
            def __init__(self, owner: _FakeResponse) -> None:
                self._owner = owner

            def get(self, key: str) -> str | None:
                if key.lower() == "content-length":
                    return self._owner._content_length
                return None

            def get_content_charset(self) -> str | None:
                return self._owner._charset

        self.headers = _Headers(self)

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def geturl(self) -> str:
        return self._url or "https://boards-api.greenhouse.io/v1/boards/x/jobs/1"

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _install_fake_opener(
    monkeypatch: pytest.MonkeyPatch, response: _FakeResponse
) -> None:
    """Patch build_opener so opener.open(...) returns the supplied response."""

    class _FakeOpener:
        def open(self, *_args: object, **_kwargs: object) -> _FakeResponse:
            return response

    monkeypatch.setattr("scripts.jd_ingest.build_opener", lambda *_h: _FakeOpener())


def test_fetch_json_api_returns_dict_for_valid_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"title": "Staff SDET", "content": "<p>JD body</p>"}'
    _install_fake_opener(monkeypatch, _FakeResponse(body=body))
    out = _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1")
    assert out == {"title": "Staff SDET", "content": "<p>JD body</p>"}


def test_fetch_json_api_returns_none_when_payload_is_not_a_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON arrays / strings / numbers must be rejected (caller wants a dict)."""
    for body in (b'["a", "b"]', b'"just a string"', b"42", b"null", b"true"):
        _install_fake_opener(monkeypatch, _FakeResponse(body=body))
        assert (
            _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1")
            is None
        )


def test_fetch_json_api_returns_none_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_opener(monkeypatch, _FakeResponse(body=b"<html>not json</html>"))
    assert (
        _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1") is None
    )


def test_fetch_json_api_returns_none_on_oversize_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server-declared Content-Length above the cap short-circuits the read."""
    huge = str(10 * 1024 * 1024)  # 10 MiB declared
    _install_fake_opener(
        monkeypatch, _FakeResponse(body=b'{"title": "x"}', content_length=huge)
    )
    assert (
        _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1") is None
    )


def test_fetch_json_api_returns_none_on_oversize_actual_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even without a declared Content-Length, body > _MAX_FETCH_BYTES rejects.

    Construct a body strictly larger than the cap so the post-read length
    check fires.
    """
    from scripts.jd_ingest import _MAX_FETCH_BYTES

    body = b"x" * (_MAX_FETCH_BYTES + 100)
    _install_fake_opener(monkeypatch, _FakeResponse(body=body))
    assert (
        _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1") is None
    )


def test_fetch_json_api_returns_none_when_url_validation_fails() -> None:
    """Invalid URL (e.g. localhost) is rejected before any network call."""
    # No opener stub: if validation didn't fire, this would try a real fetch
    # and the test would either hang or hit external network.
    assert _fetch_json_api("http://localhost/api/widget") is None
    assert _fetch_json_api("file:///etc/passwd") is None


def test_fetch_json_api_returns_none_on_opener_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any opener-level error (network failure, timeout, etc.) returns None."""

    class _RaisingOpener:
        def open(self, *_args: object, **_kwargs: object) -> _FakeResponse:
            raise RuntimeError("connection refused")

    monkeypatch.setattr("scripts.jd_ingest.build_opener", lambda *_h: _RaisingOpener())
    assert (
        _fetch_json_api("https://boards-api.greenhouse.io/v1/boards/x/jobs/1") is None
    )


# --- #247 fix-3: Playwright JD fetcher -----------------------------------


@pytest.mark.parametrize(
    "host, expected",
    [
        # Workday family — any subdomain matches.
        ("becu.wd1.myworkdayjobs.com", True),
        ("foo.bar.myworkdayjobs.com", True),
        ("myworkdayjobs.com", True),
        # Western Union exact match.
        ("careers.westernunion.com", True),
        # Non-matching hosts.
        ("careers.example.com", False),
        ("workday.com", False),  # close-but-not-matching apex
        ("not-westernunion.com", False),
        ("careers.westernunion.com.evil.example", False),  # suffix isn't a match
        ("", False),
        ("CAREERS.WESTERNUNION.COM", True),  # case-insensitive
    ],
)
def test_host_needs_javascript_render(host: str, expected: bool) -> None:
    assert _host_needs_javascript_render(host) is expected


def test_playwright_enabled_returns_false_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", raising=False)
    assert _playwright_enabled() is False


def test_playwright_enabled_returns_false_when_env_non_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "true")
    assert _playwright_enabled() is False


def test_playwright_enabled_returns_false_when_package_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: None)
    assert _playwright_enabled() is False


def test_playwright_enabled_returns_true_when_env_set_and_package_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    assert _playwright_enabled() is True


@pytest.mark.parametrize(
    "url, static_chars, expected",
    [
        # JS-rendered host: always retry regardless of static-fetch length.
        ("https://becu.wd1.myworkdayjobs.com/job/123", 50, True),
        ("https://becu.wd1.myworkdayjobs.com/job/123", 1000, True),
        ("https://careers.westernunion.com/x", 0, True),
        # Non-matching host: only retry when static came back below threshold.
        ("https://example.com/jobs/123", 100, True),
        ("https://example.com/jobs/123", 199, True),
        ("https://example.com/jobs/123", 200, False),
        ("https://example.com/jobs/123", 5000, False),
    ],
)
def test_should_use_playwright_decision(
    url: str, static_chars: int, expected: bool
) -> None:
    static = FetchedPage(
        status="fetched",
        title="t",
        description="A" * static_chars,
        notes=(),
    )
    assert _should_use_playwright(url, static) is expected


# --- _playwright_fetch_html with a fake sync_playwright -------------------


class _FakePage:
    def __init__(self, *, title: str, content: str) -> None:
        self._title = title
        self._content = content
        self.goto_calls: list[tuple[str, dict[str, object]]] = []
        self.wait_calls: list[int] = []

    def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append((url, kwargs))

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._content


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self._page = page
        self.closed = False
        self.new_page_kwargs: dict[str, object] = {}

    def new_page(self, **kwargs: object) -> _FakePage:
        self.new_page_kwargs = kwargs
        return self._page

    def close(self) -> None:
        self.closed = True


class _FakeChromium:
    def __init__(self, browser: _FakeBrowser) -> None:
        self._browser = browser
        self.launch_kwargs: dict[str, object] = {}

    def launch(self, **kwargs: object) -> _FakeBrowser:
        self.launch_kwargs = kwargs
        return self._browser


class _FakePlaywright:
    def __init__(self, chromium: _FakeChromium) -> None:
        self.chromium = chromium


class _FakeSyncPlaywrightCM:
    def __init__(self, pw: _FakePlaywright) -> None:
        self._pw = pw

    def __enter__(self) -> _FakePlaywright:
        return self._pw

    def __exit__(self, *args: object) -> None:
        return None


def _make_fake_sync_playwright(
    *, title: str = "Job Title", content: str = "<p>JD body</p>"
) -> tuple[Any, _FakeBrowser, _FakeChromium]:
    page = _FakePage(title=title, content=content)
    browser = _FakeBrowser(page)
    chromium = _FakeChromium(browser)
    pw = _FakePlaywright(chromium)
    cm = _FakeSyncPlaywrightCM(pw)

    def factory() -> _FakeSyncPlaywrightCM:
        return cm

    return factory, browser, chromium


def test_playwright_fetch_html_returns_title_and_content() -> None:
    fake_sync, _browser, _chromium = _make_fake_sync_playwright(
        title="Staff SDET", content="<p>JD body</p>"
    )
    out = _playwright_fetch_html(fake_sync, "https://example.com/job/1")
    assert out == ("Staff SDET", "<p>JD body</p>")


def test_playwright_fetch_html_passes_user_agent_and_settle_window() -> None:
    fake_sync, browser, chromium = _make_fake_sync_playwright()
    _playwright_fetch_html(fake_sync, "https://example.com/job/1")
    # Browser launched headless; user-agent forwarded to new_page.
    assert chromium.launch_kwargs == {"headless": True}
    assert "user_agent" in browser.new_page_kwargs


def test_playwright_fetch_html_truncates_oversize_content() -> None:
    big = "<p>" + ("X" * (256 * 1024 + 100)) + "</p>"
    fake_sync, _browser, _chromium = _make_fake_sync_playwright(title="t", content=big)
    out = _playwright_fetch_html(fake_sync, "https://example.com/job/1")
    assert out is not None
    _title, html = out
    assert len(html) == 256 * 1024  # _MAX_FETCH_BYTES


def test_playwright_fetch_html_returns_none_on_browser_failure() -> None:
    """Any exception during the browser dance returns None (caller falls back)."""

    class _RaisingChromium:
        def launch(self, **_kwargs: object) -> object:
            raise RuntimeError("browser launch failed")

    class _RaisingPW:
        chromium = _RaisingChromium()

    def factory() -> _FakeSyncPlaywrightCM:
        return _FakeSyncPlaywrightCM(_RaisingPW())  # type: ignore[arg-type]

    assert _playwright_fetch_html(factory, "https://example.com/job/1") is None


# --- _fetch_via_playwright wrapper ---------------------------------------


def test_fetch_via_playwright_returns_none_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: None)
    assert _fetch_via_playwright("https://example.com/job/1") is None


def test_fetch_via_playwright_returns_none_when_url_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Localhost / non-public URLs are rejected before the browser launches."""
    monkeypatch.setattr(
        "scripts.jd_ingest._import_sync_playwright", lambda: lambda: None
    )
    assert _fetch_via_playwright("http://localhost/job") is None
    assert _fetch_via_playwright("file:///etc/passwd") is None


def test_fetch_via_playwright_wraps_html_into_fetched_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    monkeypatch.setattr(
        "scripts.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: ("Staff SDET", "<p>JD body here.</p>"),
    )
    out = _fetch_via_playwright("https://example.com/job/1")
    assert out is not None
    assert out.title == "Staff SDET"
    assert "JD body here" in out.description
    assert out.notes == ("source:playwright",)
    assert out.status == "fetched"


def test_fetch_via_playwright_returns_none_when_inner_fetch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    monkeypatch.setattr(
        "scripts.jd_ingest._playwright_fetch_html", lambda _sync, _url: None
    )
    assert _fetch_via_playwright("https://example.com/job/1") is None


def test_fetch_via_playwright_returns_none_when_html_strips_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTML that strips down to whitespace-only text is treated as no content."""
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    monkeypatch.setattr(
        "scripts.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: ("title", "<p></p><div>   </div>"),
    )
    assert _fetch_via_playwright("https://example.com/job/1") is None


# --- Decision-tree integration in _fetch_job_page_metadata ---------------


def test_fetch_job_page_metadata_skips_playwright_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright path is never tried when the env var is unset."""
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", raising=False)

    def fail_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("_fetch_via_playwright must not be called")

    monkeypatch.setattr("scripts.jd_ingest._fetch_via_playwright", fail_if_called)
    monkeypatch.setattr("scripts.jd_ingest._try_board_api_fetch", lambda _u: None)
    # Stub the static fetch by feeding a known HTML shape via the fixture path
    # is too involved; instead, monkeypatch the opener so the static fetcher
    # produces a known empty result.

    class _StubOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            class _R:
                headers = type(
                    "_H",
                    (),
                    {
                        "get": staticmethod(lambda _k: None),
                        "get_content_charset": staticmethod(lambda: "utf-8"),
                    },
                )()

                def read(self, _n: int = -1) -> bytes:
                    return b"<html><body></body></html>"

                def geturl(self) -> str:
                    return "https://example.com/job/1"

                def __enter__(self) -> object:
                    return self

                def __exit__(self, *args: object) -> None:
                    return None

            return _R()

    monkeypatch.setattr("scripts.jd_ingest.build_opener", lambda *_h: _StubOpener())
    from scripts.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://example.com/job/1")
    assert result.notes != ("source:playwright",)


def test_fetch_job_page_metadata_uses_playwright_for_js_rendered_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workday URL + env opt-in => Playwright fetcher is invoked and wins."""
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    monkeypatch.setattr("scripts.jd_ingest._try_board_api_fetch", lambda _u: None)

    pw_result = FetchedPage(
        status="fetched",
        title="Staff Engineer",
        description="Real JD body fetched via headless browser. " * 10,
        notes=("source:playwright",),
    )
    captured: dict[str, str] = {}

    def fake_pw(url: str) -> FetchedPage:
        captured["url"] = url
        return pw_result

    monkeypatch.setattr("scripts.jd_ingest._fetch_via_playwright", fake_pw)

    class _EmptyOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            class _R:
                headers = type(
                    "_H",
                    (),
                    {
                        "get": staticmethod(lambda _k: None),
                        "get_content_charset": staticmethod(lambda: "utf-8"),
                    },
                )()

                def read(self, _n: int = -1) -> bytes:
                    return b"<html><body></body></html>"

                def geturl(self) -> str:
                    return "https://becu.wd1.myworkdayjobs.com/job/123"

                def __enter__(self) -> object:
                    return self

                def __exit__(self, *args: object) -> None:
                    return None

            return _R()

    monkeypatch.setattr("scripts.jd_ingest.build_opener", lambda *_h: _EmptyOpener())
    from scripts.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://becu.wd1.myworkdayjobs.com/job/123")
    assert result is pw_result
    assert captured["url"] == "https://becu.wd1.myworkdayjobs.com/job/123"


def test_fetch_job_page_metadata_falls_back_to_static_when_playwright_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright path fails => static result is returned (not silently dropped)."""
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr("scripts.jd_ingest._import_sync_playwright", lambda: object())
    monkeypatch.setattr("scripts.jd_ingest._try_board_api_fetch", lambda _u: None)
    monkeypatch.setattr("scripts.jd_ingest._fetch_via_playwright", lambda _u: None)

    body = (
        b"<html><head><title>Static Title</title></head>"
        b"<body><p>Static body</p></body></html>"
    )

    class _StaticOpener:
        def open(self, *_args: object, **_kwargs: object) -> object:
            class _R:
                headers = type(
                    "_H",
                    (),
                    {
                        "get": staticmethod(lambda _k: None),
                        "get_content_charset": staticmethod(lambda: "utf-8"),
                    },
                )()

                def read(self, _n: int = -1) -> bytes:
                    return body

                def geturl(self) -> str:
                    return "https://becu.wd1.myworkdayjobs.com/job/123"

                def __enter__(self) -> object:
                    return self

                def __exit__(self, *args: object) -> None:
                    return None

            return _R()

    monkeypatch.setattr("scripts.jd_ingest.build_opener", lambda *_h: _StaticOpener())
    from scripts.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://becu.wd1.myworkdayjobs.com/job/123")
    # Static result preserved when Playwright returns None.
    assert result.notes == ()
    assert result.title == "Static Title"
