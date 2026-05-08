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

import pytest

from scripts.jd_ingest import (
    _extract_company_name,
    _extract_role_from_title,
    _extract_role_hint,
    _fetch_greenhouse_via_api,
    _fetch_json_api,
    _fetch_workable_via_api,
    _html_to_text,
    _infer_source,
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
