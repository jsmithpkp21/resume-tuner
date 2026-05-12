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

from resume_builder.jd_ingest import (
    FetchedPage,
    _extract_company_name,
    _extract_jobposting_from_html,
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
    _resolve_host_body_selector,
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


# --- Issue #293: strip non-prose tag content (style / script / noscript) ----


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Bare style block contributes nothing.
        ("<style>.x{color:red}</style>", ""),
        # Bare script block contributes nothing.
        ("<script>alert(1)</script>", ""),
        # Bare noscript block contributes nothing.
        ("<noscript>fallback</noscript>", ""),
        # Style block with attributes (typical: type="text/css").
        ('<style type="text/css">body{margin:0}</style>', ""),
        # Script with attributes (typical: src/type/async).
        ('<script src="/x.js"></script>', ""),
        # Inline CSS rules with the noisy patterns from WU's Angular bundle —
        # smoke test for the actual real-world repro shape from issue #293.
        (
            "<style>[uib-typeahead-popup].dropdown-menu{display:block;}"
            ".uib-time input{width:50px;}</style>",
            "",
        ),
        # Mixed: real prose, style in the middle, more prose. Block-paragraph
        # behavior preserved across the elided style block (the bare `<p>`
        # form produces a single `\n` between paragraphs — the double-`\n`
        # form needs `<div><p>` stacking, which isn't on the skip-block
        # path here).
        ("<p>before</p><style>x{}</style><p>after</p>", "before\nafter"),
        # Same with `<div><p>` wrapping: skip-block elision must NOT break
        # the existing double-`\n` paragraph-separator behavior.
        (
            "<div><p>A</p></div><style>x{}</style><div><p>B</p></div>",
            "A\n\nB",
        ),
        # Case-insensitive tag names — Playwright sometimes round-trips
        # uppercase tag names depending on the source document.
        ("<STYLE>x{}</STYLE><p>kept</p>", "kept"),
        ("<Script>js</Script><p>kept</p>", "kept"),
        # Multiple skip tags in series: each contributes nothing, prose between
        # them is preserved.
        (
            "<p>A</p><style>1</style><script>2</script><noscript>3</noscript><p>B</p>",
            "A\nB",
        ),
    ],
)
def test_html_to_text_strips_non_prose_tag_content(raw: str, expected: str) -> None:
    """Issue #293: <style> / <script> / <noscript> contents must not leak
    into the extracted JD prose. Pre-fix the shared `_PlainTextHTMLParser`
    treated their text as data, so JS-rendered pages with large inline
    stylesheets (notably `careers.westernunion.com`) had their description
    excerpt dominated by CSS rules, leaving the LLM-tailoring stage with
    little JD signal to work with.
    """
    assert _html_to_text(raw) == expected


def test_html_to_text_resumes_after_skip_block_closes() -> None:
    """Regression guard: the skip-depth counter must reach 0 cleanly so a
    `<p>` after `</style>` still triggers a paragraph break. Without
    correct bookkeeping, prose AFTER a skip block could be silently
    swallowed or emitted without its leading newline.
    """
    raw = "first<style>noise</style><p>second</p>"
    assert _html_to_text(raw) == "first\nsecond"


@pytest.mark.parametrize(
    "raw, expected",
    [
        # PR #294 review: bare nested block inside <noscript> must NOT
        # emit a stray newline. Pre-fix the inner `<p>` triggered
        # handle_starttag → newline append even though its text was
        # correctly suppressed by handle_data.
        ("<noscript><p>fallback</p></noscript>", ""),
        # The same noscript wrapped between real paragraphs: surrounding
        # prose must keep its single-`\n` separator without an extra
        # blank line injected by the inner <p>.
        (
            "<p>before</p><noscript><p>fallback</p></noscript><p>after</p>",
            "before\nafter",
        ),
        # Self-closing block tag (`<br/>` style) inside a skip block —
        # handle_startendtag delegates to handle_starttag, so the same
        # guard must apply.
        ("<style>x<br/>y</style><p>kept</p>", "kept"),
        # Multiple nested block tags inside a skipped block: zero of
        # them should contribute newlines.
        ("<noscript><div><p>a</p><br/><p>b</p></div></noscript>", ""),
    ],
)
def test_html_to_text_skip_block_suppresses_inner_break_tags(
    raw: str, expected: str
) -> None:
    """Issue #293 / PR #294 review: structural break-tag newlines (`<br>`,
    `<p>`, `<div>`, etc.) inside a skipped block must not leak into the
    output. The skipped block is supposed to contribute nothing — text
    AND breaks alike.
    """
    assert _html_to_text(raw) == expected


# --- Issue #293 carve-out: JSON-LD scripts are KEPT, not stripped ---


@pytest.mark.parametrize(
    "raw, expected_substring",
    [
        # JSON-LD with the canonical type attribute is kept verbatim. This
        # is the WHOLE reason BECU's Workday page produces a tailored
        # summary — the JD body lives inside this script block, not in
        # the surrounding HTML.
        (
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org/","@type":"JobPosting",'
            '"title":"Staff SDET","hiringOrganization":{"name":"BECU"}}'
            "</script>",
            "Staff SDET",
        ),
        # Case-insensitive on the `type` attribute name and value, since
        # browsers tolerate either casing.
        (
            '<SCRIPT TYPE="APPLICATION/LD+JSON">'
            '{"title":"Engineer","name":"Acme"}</SCRIPT>',
            "Engineer",
        ),
        # JSON-LD alongside regular noisy script: the LD+JSON survives,
        # the JS code does not.
        (
            "<script>tracking_pixel(1)</script>"
            '<script type="application/ld+json">{"title":"Job"}</script>',
            '"title":"Job"',
        ),
    ],
)
def test_html_to_text_keeps_json_ld_scripts(raw: str, expected_substring: str) -> None:
    """Issue #293: `<script type="application/ld+json">` carries
    structured JD-schema data on Workday, Lever, and other structured-
    data boards — that's the actual JD body. The strip-script
    behavior must NOT include JSON-LD or BECU's Workday case regresses
    to deterministic fallback (description goes empty after extraction).
    """
    out = _html_to_text(raw)
    assert expected_substring in out


def test_html_to_text_strips_non_json_ld_scripts() -> None:
    """Negative case: regular `<script>` tags (no `type` or default
    `text/javascript`) are still stripped. Only JSON-LD is carved out.
    """
    assert _html_to_text("<script>alert(1)</script>") == ""
    assert _html_to_text('<script type="text/javascript">x()</script>') == ""
    assert _html_to_text('<script type="module">import x</script>') == ""


# --- Issue #293 item 2: structured JobPosting JSON-LD extraction ----


def test_extract_jobposting_returns_none_when_no_json_ld() -> None:
    """No JSON-LD ⇒ caller falls back to `_html_to_text`."""
    assert _extract_jobposting_from_html("<html><body>nope</body></html>") is None
    assert _extract_jobposting_from_html("") is None


def test_extract_jobposting_returns_none_when_no_jobposting_block() -> None:
    """JSON-LD present but no `@type=JobPosting` object ⇒ None.

    Page chrome metadata (WebPage, BreadcrumbList, Organization, etc.)
    on its own is not actionable JD signal.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"WebPage","name":"Careers"}'
        "</script>"
    )
    assert _extract_jobposting_from_html(html) is None


def test_extract_jobposting_returns_prose_for_top_level_block() -> None:
    """Canonical Workday-style JSON-LD (BECU shape): JobPosting at root,
    `description` field is HTML-formatted JD body.
    """
    html = (
        '<script type="application/ld+json">'
        "{"
        '"@context":"https://schema.org",'
        '"@type":"JobPosting",'
        '"title":"Staff Software Developer Engineer in Test",'
        '"hiringOrganization":{"@type":"Organization",'
        '"name":"Boeing Employees\' Credit Union"},'
        '"jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",'
        '"addressLocality":"Remote","addressRegion":"WA",'
        '"addressCountry":"United States of America"}},'
        '"employmentType":"FULL_TIME",'
        '"description":"<p>Build performance test frameworks for BECU.</p>"'
        "}"
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    # Grounding signals all present.
    assert "Staff Software Developer Engineer in Test" in out
    assert "Boeing Employees' Credit Union" in out
    assert "Remote, WA" in out
    assert "Full Time" in out
    # Description HTML stripped to plain prose.
    assert "Build performance test frameworks for BECU." in out
    assert "<p>" not in out


def test_extract_jobposting_returns_prose_for_graph_array_shape() -> None:
    """Western Union shape: `@graph` array containing WebPage,
    BreadcrumbList, *and* the JobPosting (or a separate block on the
    same page). The walker must traverse the array and find the
    JobPosting regardless of position.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@graph":[{"@type":"WebPage","name":"Page noise"},'
        '{"@type":"BreadcrumbList","itemListElement":[]}]}'
        "</script>"
        '<script type="application/ld+json">'
        "{"
        '"@type":"JobPosting",'
        '"title":"Staff Software Engineer",'
        '"hiringOrganization":{"name":"Western Union"},'
        '"jobLocation":{"address":{"addressLocality":"Austin",'
        '"addressRegion":"TX"}},'
        '"description":"<p>Western Union is seeking a Staff Software Engineer.</p>"'
        "}"
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "Western Union" in out
    assert "Austin, TX" in out
    assert "Staff Software Engineer" in out
    assert "Western Union is seeking a Staff Software Engineer." in out


def test_extract_jobposting_handles_type_as_list() -> None:
    """schema.org `@type` may be `["JobPosting", "Thing"]` per JSON-LD spec."""
    html = (
        '<script type="application/ld+json">'
        '{"@type":["Thing","JobPosting"],'
        '"title":"Engineer",'
        '"hiringOrganization":"Acme",'
        '"description":"role text"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "Engineer" in out
    assert "Acme" in out
    assert "role text" in out


def test_extract_jobposting_handles_string_hiring_organization() -> None:
    """Some boards emit `hiringOrganization` as a plain string instead
    of the canonical `{name, @type:Organization}` dict shape.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting",'
        '"title":"SWE",'
        '"hiringOrganization":"Acme Corp",'
        '"description":"text"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "Acme Corp" in out


def test_extract_jobposting_handles_jobLocation_as_list() -> None:
    """Multi-location postings: `jobLocation` is a list. Take the first
    location; that's the canonical site for the role.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting",'
        '"title":"SWE","hiringOrganization":"Acme",'
        '"jobLocation":['
        '{"address":{"addressLocality":"Austin","addressRegion":"TX"}},'
        '{"address":{"addressLocality":"Remote"}}'
        "],"
        '"description":"text"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "Austin, TX" in out


def test_extract_jobposting_handles_employmentType_as_list() -> None:
    """`employmentType` can be a list (e.g. `["FULL_TIME","CONTRACTOR"]`)."""
    html = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting",'
        '"title":"SWE","hiringOrganization":"Acme",'
        '"employmentType":["FULL_TIME","CONTRACTOR"],'
        '"description":"text"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "Full Time" in out
    assert "Contractor" in out


def test_extract_jobposting_skips_malformed_json_blocks() -> None:
    """A malformed JSON-LD block must not break parsing — try the next
    block. Real-world repro: trailing comma in handcrafted JSON-LD.
    """
    html = (
        '<script type="application/ld+json">{not json,}</script>'
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"SWE",'
        '"hiringOrganization":"Acme","description":"text"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "SWE" in out
    assert "Acme" in out


def test_extract_jobposting_returns_first_matching_block() -> None:
    """Multiple JobPosting blocks (rare — page lists multiple jobs):
    use the first. The URL is specific to one job.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"First","hiringOrganization":"A",'
        '"description":"first"}'
        "</script>"
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"Second","hiringOrganization":"B",'
        '"description":"second"}'
        "</script>"
    )
    out = _extract_jobposting_from_html(html)
    assert out is not None
    assert "First" in out
    assert "Second" not in out


def test_extract_jobposting_returns_none_when_jobposting_has_no_useful_fields() -> None:
    """Defensive: a JobPosting object that's structurally valid but
    contains no actionable fields (no title, org, location, type, OR
    description) returns None so the caller falls back.
    """
    html = (
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","datePosted":"2026-01-01"}'
        "</script>"
    )
    assert _extract_jobposting_from_html(html) is None


def test_fetch_via_playwright_prefers_jobposting_jsonld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: when Playwright HTML contains JobPosting JSON-LD, the
    fetched description is the structured prose (not the raw text
    extraction), and the notes record `source:jsonld+jobposting`.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )

    html_with_posting = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"Staff SWE",'
        '"hiringOrganization":{"name":"Western Union"},'
        '"jobLocation":{"address":{"addressLocality":"Austin","addressRegion":"TX"}},'
        '"description":"<p>Build retail engineering platform.</p>"}'
        "</script>"
        "<p>Page chrome that should NOT leak through.</p>"
        "</body></html>"
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _pw, _url: ("Page Title", html_with_posting, None),
    )

    result = _fetch_via_playwright(
        "https://careers.westernunion.com/job-details/123/staff-engineer/"
    )
    assert result is not None
    assert "Western Union" in result.description
    assert "Austin, TX" in result.description
    assert "Staff SWE" in result.description
    assert "Build retail engineering platform." in result.description
    # Page chrome from non-JobPosting HTML is NOT in the description.
    assert "Page chrome that should NOT leak through" not in result.description
    # Note record signals which extraction path was used.
    assert "source:jsonld+jobposting" in result.notes
    assert "source:playwright" in result.notes


def test_fetch_via_playwright_falls_back_to_html_text_when_no_jobposting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the page has no JobPosting JSON-LD (or only WebPage chrome),
    the fetcher falls back to `_html_to_text` and the notes do NOT
    include the jsonld marker — preserves backwards compatibility for
    pages without structured data (Greenhouse iframes, hand-rolled
    boards).
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )

    html_without_posting = (
        "<html><body>"
        "<h1>Senior Software Engineer</h1>"
        "<p>Plain HTML JD body, no JSON-LD here.</p>"
        "</body></html>"
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _pw, _url: ("title", html_without_posting, None),
    )

    result = _fetch_via_playwright("https://example.com/job/123")
    assert result is not None
    assert "Senior Software Engineer" in result.description
    assert "Plain HTML JD body" in result.description
    assert "source:jsonld+jobposting" not in result.notes
    assert "source:playwright" in result.notes


def test_try_board_api_fetch_dispatches_to_greenhouse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_json(api_url: str) -> dict[str, str]:
        captured["api_url"] = api_url
        return {"title": "Senior SWE", "content": "<p>JD body here</p>"}

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_json_api", fake_json)

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

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_json_api", fake_json)
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

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_json_api", fake_json)

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

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_json_api", fake_json)
    assert _try_board_api_fetch(url) is None


def test_try_board_api_fetch_returns_none_on_api_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the API itself fails, dispatch returns None for HTML fallback."""

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_json_api", lambda _url: None)
    assert _try_board_api_fetch("https://boards.greenhouse.io/acme/jobs/12345") is None
    assert _try_board_api_fetch("https://apply.workable.com/acme/j/abc123/") is None


def test_fetch_greenhouse_via_api_returns_none_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An API call that returns an empty / title-less / content-less payload
    should be treated as a failure so the caller falls back to HTML."""
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_json_api",
        lambda _u: {"title": "", "content": ""},
    )
    assert _fetch_greenhouse_via_api(board="acme", job_id="123") is None


def test_fetch_workable_via_api_returns_none_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_json_api",
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
        "resume_builder.jd_ingest._fetch_json_api",
        lambda _u: {"title": "Senior SWE", "content": ""},
    )
    assert _fetch_greenhouse_via_api(board="acme", job_id="123") is None


def test_fetch_workable_via_api_returns_none_on_title_only_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same rationale as the Greenhouse equivalent — require a description."""
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_json_api",
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

    monkeypatch.setattr(
        "resume_builder.jd_ingest.build_opener", lambda *_h: _FakeOpener()
    )


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
    from resume_builder.jd_ingest import _MAX_FETCH_BYTES

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

    monkeypatch.setattr(
        "resume_builder.jd_ingest.build_opener", lambda *_h: _RaisingOpener()
    )
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
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: None
    )
    assert _playwright_enabled() is False


def test_playwright_enabled_returns_true_when_env_set_and_package_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
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


class _FakeLocator:
    """Minimal stand-in for a Playwright Locator / FrameLocator chain.

    Supports the surface ``_extract_via_host_body_selector`` exercises:
    ``page.locator(sel).text_content(timeout=…)`` and
    ``page.frame_locator(frame_sel).locator(inner_sel).text_content(…)``.
    Tests configure the per-selector return via the parent ``_FakePage``.
    """

    def __init__(self, page: _FakePage, *, frame_target: str | None = None) -> None:
        self._page = page
        self._frame_target = frame_target

    def locator(self, sel: str) -> _FakeLocator:
        # When chained off a frame_locator, record the (frame, inner)
        # pair so tests can assert the iframe path was taken.
        if self._frame_target is not None:
            self._page.frame_locator_calls.append((self._frame_target, sel))
            self._page._pending_lookup = ("frame", self._frame_target, sel)
        else:
            self._page._pending_lookup = ("page", sel)
        return self

    def text_content(self, timeout: int | None = None) -> str | None:
        self._page.text_content_calls.append(timeout)
        lookup = self._page._pending_lookup
        if lookup is None:
            return None
        key: tuple[str, ...]
        if lookup[0] == "frame":
            key = ("frame", lookup[1], lookup[2])
        else:
            key = ("page", lookup[1])
        result = self._page.text_content_map.get(key, self._page.default_text_content)
        if isinstance(result, BaseException):
            raise result
        return result


class _FakePage:
    def __init__(self, *, title: str, content: str) -> None:
        self._title = title
        self._content = content
        self.goto_calls: list[tuple[str, dict[str, object]]] = []
        self.wait_calls: list[int] = []
        # Per-selector text_content mapping for the issue #298 selector
        # path. Keys are either ``("page", sel)`` or
        # ``("frame", frame_sel, inner_sel)``; missing keys fall back to
        # ``default_text_content``. A BaseException value is raised
        # (used to exercise the graceful-failure branch).
        self.text_content_map: dict[tuple[str, ...], str | None | BaseException] = {}
        self.default_text_content: str | None = None
        self.text_content_calls: list[int | None] = []
        self.frame_locator_calls: list[tuple[str, str]] = []
        self._pending_lookup: tuple[str, ...] | None = None

    def goto(self, url: str, **kwargs: object) -> None:
        self.goto_calls.append((url, kwargs))

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls.append(ms)

    def title(self) -> str:
        return self._title

    def content(self) -> str:
        return self._content

    def locator(self, sel: str) -> _FakeLocator:
        loc = _FakeLocator(self)
        return loc.locator(sel)

    def frame_locator(self, frame_sel: str) -> _FakeLocator:
        return _FakeLocator(self, frame_target=frame_sel)


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
    # Body snippet slot is None when no host selector is configured for
    # the URL's host. Issue #298.
    assert out == ("Staff SDET", "<p>JD body</p>", None)


def test_playwright_fetch_html_passes_user_agent_and_settle_window() -> None:
    fake_sync, browser, chromium = _make_fake_sync_playwright()
    _playwright_fetch_html(fake_sync, "https://example.com/job/1")
    # Browser launched headless; user-agent forwarded to new_page.
    assert chromium.launch_kwargs == {"headless": True}
    assert "user_agent" in browser.new_page_kwargs


def test_playwright_fetch_html_truncates_oversize_content() -> None:
    """Issue #293 item 2: Playwright now uses the larger
    _MAX_PLAYWRIGHT_HTML_BYTES cap (4 MB) instead of the 256 KB static
    cap, so JS-rendered boards with late-loaded JSON-LD JobPosting
    blocks (e.g. WU careers at ~1.4 MB offset) can be searched. The
    bound is still enforced — pages exceeding 4 MB are clipped — but
    the threshold is high enough that real boards aren't affected.
    """
    from resume_builder.jd_ingest import _MAX_PLAYWRIGHT_HTML_BYTES

    big = "<p>" + ("X" * (_MAX_PLAYWRIGHT_HTML_BYTES + 100)) + "</p>"
    fake_sync, _browser, _chromium = _make_fake_sync_playwright(title="t", content=big)
    out = _playwright_fetch_html(fake_sync, "https://example.com/job/1")
    assert out is not None
    _title, html, _body = out
    assert len(html) == _MAX_PLAYWRIGHT_HTML_BYTES
    # Content under the cap is returned unmodified.
    smaller = "<p>" + ("X" * 1024) + "</p>"
    fake_sync2, _b2, _c2 = _make_fake_sync_playwright(title="t", content=smaller)
    out2 = _playwright_fetch_html(fake_sync2, "https://example.com/job/2")
    assert out2 is not None
    assert len(out2[1]) == len(smaller)


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
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: None
    )
    assert _fetch_via_playwright("https://example.com/job/1") is None


def test_fetch_via_playwright_returns_none_when_url_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Localhost / non-public URLs are rejected before the browser launches."""
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: lambda: None
    )
    assert _fetch_via_playwright("http://localhost/job") is None
    assert _fetch_via_playwright("file:///etc/passwd") is None


def test_fetch_via_playwright_wraps_html_into_fetched_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: ("Staff SDET", "<p>JD body here.</p>", None),
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
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html", lambda _sync, _url: None
    )
    assert _fetch_via_playwright("https://example.com/job/1") is None


def test_fetch_via_playwright_returns_none_when_html_strips_to_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTML that strips down to whitespace-only text is treated as no content."""
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: ("title", "<p></p><div>   </div>", None),
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

    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_via_playwright", fail_if_called
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._try_board_api_fetch", lambda _u: None
    )
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

    monkeypatch.setattr(
        "resume_builder.jd_ingest.build_opener", lambda *_h: _StubOpener()
    )
    from resume_builder.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://example.com/job/1")
    assert result.notes != ("source:playwright",)


def test_fetch_job_page_metadata_uses_playwright_for_js_rendered_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workday URL + env opt-in => Playwright fetcher is invoked and wins."""
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._try_board_api_fetch", lambda _u: None
    )

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

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_via_playwright", fake_pw)

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

    monkeypatch.setattr(
        "resume_builder.jd_ingest.build_opener", lambda *_h: _EmptyOpener()
    )
    from resume_builder.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://becu.wd1.myworkdayjobs.com/job/123")
    assert result is pw_result
    assert captured["url"] == "https://becu.wd1.myworkdayjobs.com/job/123"


def test_fetch_job_page_metadata_falls_back_to_static_when_playwright_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright path fails => static result is returned (not silently dropped)."""
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._try_board_api_fetch", lambda _u: None
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_via_playwright", lambda _u: None
    )

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

    monkeypatch.setattr(
        "resume_builder.jd_ingest.build_opener", lambda *_h: _StaticOpener()
    )
    from resume_builder.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata("https://becu.wd1.myworkdayjobs.com/job/123")
    # Static result preserved when Playwright returns None.
    assert result.notes == ()
    assert result.title == "Static Title"


# --- Issue #281: static-fetch failures must fall through to Playwright -----


@pytest.mark.parametrize(
    "static_failure_notes, label",
    [
        (("fetch_failed:ResponseTooLarge",), "response_too_large"),
        (("fetch_failed:ContentTooLarge",), "content_too_large_header"),
        (("fetch_failed:URLError",), "static_exception"),
    ],
)
def test_fetch_job_page_metadata_falls_through_to_playwright_on_static_failure(
    monkeypatch: pytest.MonkeyPatch,
    static_failure_notes: tuple[str, ...],
    label: str,
) -> None:
    """Issue #281: when the static fetch fails outright, Playwright must
    still be tried for allowlisted JS-rendered hosts.

    Pre-fix the static-fetch failure paths (ResponseTooLarge,
    ContentTooLarge, exception) early-returned a `fetch_failed`
    FetchedPage and never invoked the Playwright fallback. This was
    the root cause of v4's `careers.westernunion.com` cases all going
    deterministic — the host's bundled Angular SPA exceeds 256 KB on
    static fetch, so the body-too-large path fired and Playwright
    never ran despite the host being on `_JS_RENDERED_EXACT_HOSTS`.
    """
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._try_board_api_fetch", lambda _u: None
    )

    static_failure = FetchedPage(
        status="fetch_failed",
        title="",
        description="",
        notes=static_failure_notes,
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_static_job_page_metadata",
        lambda _u: static_failure,
    )

    pw_result = FetchedPage(
        status="fetched",
        title="WU Staff SWE",
        description="Real JD body recovered via headless browser. " * 8,
        notes=("source:playwright",),
    )
    captured: dict[str, str] = {}

    def fake_pw(url: str) -> FetchedPage:
        captured["url"] = url
        return pw_result

    monkeypatch.setattr("resume_builder.jd_ingest._fetch_via_playwright", fake_pw)
    from resume_builder.jd_ingest import _fetch_job_page_metadata

    url = "https://careers.westernunion.com/job-details/12345/staff-engineer/"
    result = _fetch_job_page_metadata(url)
    assert result is pw_result, f"failed for {label}: got {result!r}"
    assert captured["url"] == url


def test_fetch_job_page_metadata_returns_static_failure_when_playwright_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #281 negative case: with Playwright disabled, static failure
    is returned as-is. The fix only adds a fallthrough when Playwright is
    actually available; default behavior for callers who haven't opted in
    must remain unchanged.
    """
    monkeypatch.delenv("RESUME_BUILDER_JOB_PAGE_FIXTURE", raising=False)
    monkeypatch.delenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", raising=False)
    monkeypatch.setattr(
        "resume_builder.jd_ingest._try_board_api_fetch", lambda _u: None
    )

    static_failure = FetchedPage(
        status="fetch_failed",
        title="",
        description="",
        notes=("fetch_failed:ResponseTooLarge",),
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_static_job_page_metadata",
        lambda _u: static_failure,
    )

    def _should_not_be_called(_url: str) -> FetchedPage | None:
        raise AssertionError("_fetch_via_playwright must not run when env disabled")

    monkeypatch.setattr(
        "resume_builder.jd_ingest._fetch_via_playwright", _should_not_be_called
    )
    from resume_builder.jd_ingest import _fetch_job_page_metadata

    result = _fetch_job_page_metadata(
        "https://careers.westernunion.com/job-details/12345/staff-engineer/"
    )
    assert result.status == "fetch_failed"
    assert result.notes == ("fetch_failed:ResponseTooLarge",)


# --- Issue #298: per-host JD body selectors ------------------------------


def test_resolve_host_body_selector_exact_match_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTORS",
        {"radarfirst.com": "iframe#grnhse_iframe >> #content"},
    )
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})
    assert (
        _resolve_host_body_selector("radarfirst.com")
        == "iframe#grnhse_iframe >> #content"
    )


def test_resolve_host_body_selector_family_suffix_matches_subdomain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTORS", {})
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES",
        {"example.com": "div.jd-body"},
    )
    assert _resolve_host_body_selector("board.example.com") == "div.jd-body"
    assert _resolve_host_body_selector("example.com") == "div.jd-body"


def test_resolve_host_body_selector_returns_none_when_no_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTORS", {})
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})
    assert _resolve_host_body_selector("anywhere.example") is None
    assert _resolve_host_body_selector("") is None


def test_resolve_host_body_selector_picks_longest_matching_family_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When multiple family suffixes match, the longest (most specific)
    wins — regardless of dict insertion order. PR #313 review.
    """
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTORS", {})
    # Broad entry inserted FIRST, specific entry inserted SECOND: longest
    # still wins.
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES",
        {"example.com": "div.broad", "jobs.example.com": "div.specific"},
    )
    assert _resolve_host_body_selector("board.jobs.example.com") == "div.specific"
    assert _resolve_host_body_selector("jobs.example.com") == "div.specific"
    # Host that only matches the broad entry still resolves correctly.
    assert _resolve_host_body_selector("other.example.com") == "div.broad"

    # Reverse insertion order: specific first, broad second. Result
    # must not change.
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES",
        {"jobs.example.com": "div.specific", "example.com": "div.broad"},
    )
    assert _resolve_host_body_selector("board.jobs.example.com") == "div.specific"


def test_resolve_host_body_selector_does_not_truncate_ipv6_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`urlparse(url).hostname` for an IPv6 URL returns the address
    without brackets, e.g. ``'2001:db8::1'``. The previous defensive
    ``host.split(':', 1)[0]`` would have truncated this to ``'2001'``.
    PR #313 review round 3.
    """
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTORS",
        {"2001:db8::1": "div.jd-body"},
    )
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})
    # The exact-host map lookup only works if the colons in the IPv6
    # address were preserved through normalization.
    assert _resolve_host_body_selector("2001:db8::1") == "div.jd-body"


def test_host_needs_javascript_render_does_not_truncate_ipv6_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parallel to `test_resolve_host_body_selector_does_not_truncate_ipv6_hosts`:
    the JS-render allowlist check used the same ``host.split(':', 1)[0]``
    defensive truncation and would silently misroute IPv6 hosts (e.g.
    ``'2001:db8::1'`` -> ``'2001'``). Issue #317.
    """
    monkeypatch.setattr(
        "resume_builder.jd_ingest._JS_RENDERED_EXACT_HOSTS",
        ("2001:db8::1",),
    )
    monkeypatch.setattr("resume_builder.jd_ingest._JS_RENDERED_HOST_FAMILIES", ())
    # Exact-host match only works if colons survived normalization.
    assert _host_needs_javascript_render("2001:db8::1") is True
    # And the negative path: an IPv6 host NOT in the allowlist must
    # not get truncated into a prefix that *would* match the allowlist
    # (regression guard for the silent-misroute failure mode).
    monkeypatch.setattr(
        "resume_builder.jd_ingest._JS_RENDERED_EXACT_HOSTS",
        ("2001",),
    )
    assert _host_needs_javascript_render("2001:db8::1") is False


def test_fetch_via_playwright_uses_host_body_selector_when_no_jsonld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selector path runs ONLY when JSON-LD JobPosting is absent. Notes
    record `source:host-selector:<host>` for observability. Issue #298.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: (
            "RadarFirst Careers",
            "<html><body><p>page chrome no jsonld here</p></body></html>",
            "Staff Backend Engineer\n\nBuild the platform.",
        ),
    )
    result = _fetch_via_playwright("https://radarfirst.com/?gh_jid=123")
    assert result is not None
    assert "Staff Backend Engineer" in result.description
    assert "Build the platform." in result.description
    # Page chrome from the surrounding HTML must NOT leak through —
    # the selector snippet is the sole grounding source.
    assert "page chrome" not in result.description
    assert "source:playwright" in result.notes
    assert "source:host-selector:radarfirst.com" in result.notes
    assert "source:jsonld+jobposting" not in result.notes


def test_fetch_via_playwright_host_body_selector_preserves_literal_angle_brackets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selector snippet is plain text already (Playwright `text_content()`).
    Literal ``<...>`` sequences in the JD (e.g. ``<Company>`` placeholder
    text, or ``a < b`` prose) must NOT be consumed by an HTML parser on
    the selector path — they would silently disappear when routed
    through `_html_to_text`. PR #313 review.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    snippet = "Hello from <Company>! Edge condition: a < b in formula."
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: (
            "title",
            "<html><body><p>page chrome</p></body></html>",
            snippet,
        ),
    )
    result = _fetch_via_playwright("https://radarfirst.com/?gh_jid=123")
    assert result is not None
    # All three angle-bracket-bearing tokens survive intact:
    assert "<Company>" in result.description
    assert "a < b" in result.description
    assert "in formula." in result.description
    assert "source:host-selector:radarfirst.com" in result.notes


def test_fetch_via_playwright_host_body_selector_strips_surrounding_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright `text_content()` often returns text with surrounding
    whitespace from source-indentation. The selector path must produce
    a trimmed `description` — both for consistency with the HTML path
    and so the description-excerpt budget downstream gets useful chars
    instead of leading whitespace. PR #313 review round 3.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    # Realistic shape: surrounding whitespace + interior newlines.
    snippet = "\n\n    Staff Backend Engineer\n\n    Build the platform.\n  \n"
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: ("title", "<html><body/></html>", snippet),
    )
    result = _fetch_via_playwright("https://radarfirst.com/?gh_jid=123")
    assert result is not None
    assert result.description == result.description.strip()
    assert result.description.startswith("Staff Backend Engineer")
    assert result.description.endswith("Build the platform.")


def test_fetch_via_playwright_prefers_jsonld_over_host_body_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON-LD JobPosting still wins even when a body snippet is
    available — preserves the v7 12/12 LLM-tailored matrix. Issue #298.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    html_with_posting = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"Staff Backend Engineer",'
        '"hiringOrganization":{"name":"RadarFirst"},'
        '"description":"<p>JSON-LD prose wins.</p>"}'
        "</script></body></html>"
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: (
            "title",
            html_with_posting,
            "selector snippet should be ignored",
        ),
    )
    result = _fetch_via_playwright("https://radarfirst.com/?gh_jid=123")
    assert result is not None
    assert "JSON-LD prose wins." in result.description
    assert "selector snippet should be ignored" not in result.description
    assert "source:jsonld+jobposting" in result.notes
    assert "source:host-selector:radarfirst.com" not in result.notes


def test_fetch_via_playwright_falls_back_to_html_text_when_selector_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selector returned None (page redesigned / element absent): the
    fetcher falls back to `_html_to_text(content_html)` without raising
    and without emitting the host-selector note. Issue #298.
    """
    monkeypatch.setenv("RESUME_BUILDER_ENABLE_PLAYWRIGHT", "1")
    monkeypatch.setattr(
        "resume_builder.jd_ingest._import_sync_playwright", lambda: object()
    )
    monkeypatch.setattr(
        "resume_builder.jd_ingest._playwright_fetch_html",
        lambda _sync, _url: (
            "title",
            "<html><body><p>Plain HTML fallback prose.</p></body></html>",
            None,
        ),
    )
    result = _fetch_via_playwright("https://radarfirst.com/?gh_jid=123")
    assert result is not None
    assert "Plain HTML fallback prose." in result.description
    assert "source:playwright" in result.notes
    assert all("host-selector" not in n for n in result.notes)
    assert "source:jsonld+jobposting" not in result.notes


def test_playwright_fetch_html_uses_iframe_chained_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`iframe X >> Y` selector form routes through `frame_locator(X)
    .locator(Y).text_content()`. Issue #298.
    """
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTORS",
        {"example.com": "iframe#grnhse_iframe >> #content"},
    )
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})

    fake_sync, browser, _chromium = _make_fake_sync_playwright(
        title="t", content="<html><body><iframe id='grnhse_iframe'/></body></html>"
    )
    # Configure the frame-traversed selector to return real JD text.
    page = browser._page
    page.text_content_map[("frame", "iframe#grnhse_iframe", "#content")] = (
        "Senior Backend Engineer — owns ingestion pipelines."
    )

    out = _playwright_fetch_html(fake_sync, "https://example.com/jobs/1")
    assert out is not None
    _title, _html, body_snippet = out
    assert body_snippet == "Senior Backend Engineer — owns ingestion pipelines."
    # frame_locator was called with the iframe selector AND the inner
    # locator was called with the post-`>>` selector.
    assert page.frame_locator_calls == [("iframe#grnhse_iframe", "#content")]


def test_playwright_fetch_html_uses_plain_page_selector_without_iframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No `iframe` segment -> `page.locator(...).text_content()`. Issue #298."""
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTORS",
        {"example.com": "div.jd-body"},
    )
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})

    fake_sync, browser, _chromium = _make_fake_sync_playwright(
        title="t", content="<html><body><div class='jd-body'>JD</div></body></html>"
    )
    page = browser._page
    page.text_content_map[("page", "div.jd-body")] = "Plain page selector text."

    out = _playwright_fetch_html(fake_sync, "https://example.com/jobs/1")
    assert out is not None
    _title, _html, body_snippet = out
    assert body_snippet == "Plain page selector text."
    # No frame traversal occurred.
    assert page.frame_locator_calls == []


def test_playwright_fetch_html_selector_failure_yields_none_snippet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Selector raises (e.g. timeout, element absent): the body_snippet
    slot is None and `_playwright_fetch_html` still returns the (title,
    html, None) 3-tuple — never re-raises. Issue #298.
    """
    monkeypatch.setattr(
        "resume_builder.jd_ingest._HOST_BODY_SELECTORS",
        {"example.com": "div.jd-body"},
    )
    monkeypatch.setattr("resume_builder.jd_ingest._HOST_BODY_SELECTOR_FAMILIES", {})

    fake_sync, browser, _chromium = _make_fake_sync_playwright(
        title="t", content="<html><body><p>JD</p></body></html>"
    )
    page = browser._page
    page.text_content_map[("page", "div.jd-body")] = TimeoutError("selector timed out")

    out = _playwright_fetch_html(fake_sync, "https://example.com/jobs/1")
    assert out is not None
    _title, _html, body_snippet = out
    assert body_snippet is None
