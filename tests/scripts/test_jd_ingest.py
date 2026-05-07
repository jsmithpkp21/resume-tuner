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
    _infer_source,
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
