"""Tests for `job_apply_kit.ats_inference.infer_ats_tenant`.

Coverage: each supported ATS family with a representative real-world
URL from the user's captures, plus boundary cases (apex domain hits,
empty paths, unknown hosts, malformed inputs).
"""

from __future__ import annotations

import pytest

from job_apply_kit import infer_ats_tenant


class TestWorkday:
    """Workday tenants live in the leftmost subdomain ahead of the
    workday host suffix. BECU and WU captures are the real-world
    examples from `data/applications/_capture/`.
    """

    def test_becu_wd1(self) -> None:
        # Real BECU apply URL pattern (Workday wd1 cluster).
        url = (
            "https://becu.wd1.myworkdayjobs.com/External/job/Seattle/Staff-SDET_R12345"
        )
        assert infer_ats_tenant(url) == ("workday", "becu")

    def test_wu_wd5(self) -> None:
        # Real Western Union apply URL pattern.
        url = "https://westernunion.wd5.myworkdayjobs.com/en-US/WU_External/job/SDET-II_R98765"
        assert infer_ats_tenant(url) == ("workday", "westernunion")

    def test_workdayjobs_com_alias(self) -> None:
        # Some tenants use the `.workdayjobs.com` alias instead of
        # `.myworkdayjobs.com`. Same tenant-extraction logic.
        url = "https://acme.wd3.workdayjobs.com/Careers/job/123"
        assert infer_ats_tenant(url) == ("workday", "acme")

    def test_apex_workday_host_unsupported(self) -> None:
        # `myworkdayjobs.com` with no subdomain has no tenant to
        # extract — the suffix-strip leaves an empty prefix.
        url = "https://myworkdayjobs.com/something"
        assert infer_ats_tenant(url) == (None, None)

    def test_cluster_apex_returns_none(self) -> None:
        # `wd1.myworkdayjobs.com` is a Workday cluster apex, not a
        # tenant-specific URL. Without the cluster-label guard we
        # would mis-classify it as tenant=`wd1` and write credentials
        # under the cluster ID instead of the real tenant. (PR #361
        # review.)
        for cluster in ("wd1", "wd5", "wd103"):
            url = f"https://{cluster}.myworkdayjobs.com/External/job"
            assert infer_ats_tenant(url) == (None, None), (
                f"cluster-apex {cluster}.myworkdayjobs.com should not "
                f"resolve to a workday tenant"
            )

    def test_cluster_label_case_insensitive(self) -> None:
        # Just in case Workday ever returns mixed-case in the host.
        url = "https://WD2.myworkdayjobs.com/x"
        assert infer_ats_tenant(url) == (None, None)


class TestWorkable:
    """Workable apply URLs follow `apply.workable.com/<tenant>/j/<id>/`."""

    def test_murmuration(self) -> None:
        # Real Murmuration apply URL pattern (from the captures).
        url = "https://apply.workable.com/murmuration/j/ABCDEF1234/"
        assert infer_ats_tenant(url) == ("workable", "murmuration")

    def test_workable_with_query_string(self) -> None:
        url = "https://apply.workable.com/some-co/j/XYZ/?utm_source=linkedin"
        assert infer_ats_tenant(url) == ("workable", "some-co")

    def test_workable_apex_no_path(self) -> None:
        # `apply.workable.com` with no path segments — no tenant.
        url = "https://apply.workable.com/"
        assert infer_ats_tenant(url) == (None, None)

    def test_workable_marketing_host_ignored(self) -> None:
        # Only `apply.workable.com` is a job-board host. `www.workable.com`
        # and `help.workable.com` are not — should be treated as unknown.
        url = "https://www.workable.com/jobs/123"
        assert infer_ats_tenant(url) == (None, None)


class TestGreenhouse:
    """Greenhouse boards live at `boards.greenhouse.io/<tenant>/...`
    and the newer `job-boards.greenhouse.io/<tenant>/...`."""

    def test_boards_greenhouse(self) -> None:
        url = "https://boards.greenhouse.io/exampleco/jobs/4567890"
        assert infer_ats_tenant(url) == ("greenhouse", "exampleco")

    def test_job_boards_greenhouse(self) -> None:
        # The newer Greenhouse hostname uses the same path-slug shape.
        url = "https://job-boards.greenhouse.io/another-co/jobs/1234"
        assert infer_ats_tenant(url) == ("greenhouse", "another-co")

    def test_greenhouse_apex_no_path(self) -> None:
        url = "https://boards.greenhouse.io/"
        assert infer_ats_tenant(url) == (None, None)


class TestICIMS:
    """iCIMS tenants use the leftmost subdomain (e.g.
    `careers-acme.icims.com`)."""

    def test_icims_subdomain(self) -> None:
        url = "https://careers-acme.icims.com/jobs/9999"
        assert infer_ats_tenant(url) == ("icims", "careers-acme")

    def test_icims_apex_unsupported(self) -> None:
        url = "https://icims.com/jobs/1"
        assert infer_ats_tenant(url) == (None, None)


class TestUnknown:
    """Anything not matched returns (None, None) — caller prompts."""

    def test_smashfly_returns_none(self) -> None:
        # SmashFly redirects to Workday in practice (the user has hit
        # this for at least one role). At the redirect-source URL we
        # return None; once the redirect lands on the Workday URL the
        # workday handler picks it up.
        url = "https://careers-smashfly.example.com/job/123"
        assert infer_ats_tenant(url) == (None, None)

    def test_company_career_site(self) -> None:
        url = "https://careers.example.com/jobs/123"
        assert infer_ats_tenant(url) == (None, None)

    def test_empty_url(self) -> None:
        assert infer_ats_tenant("") == (None, None)

    def test_no_scheme(self) -> None:
        # urlparse handles this — hostname comes back empty.
        assert infer_ats_tenant("just a string") == (None, None)


@pytest.mark.parametrize(
    ("url", "expected_ats"),
    [
        ("https://becu.wd1.myworkdayjobs.com/x", "workday"),
        ("https://apply.workable.com/co/j/X/", "workable"),
        ("https://boards.greenhouse.io/co/jobs/1", "greenhouse"),
        ("https://co.icims.com/jobs/1", "icims"),
    ],
)
def test_supported_families_resolve_to_named_family(
    url: str, expected_ats: str
) -> None:
    """Smoke test: every supported family returns its family string."""
    ats, tenant = infer_ats_tenant(url)
    assert ats == expected_ats
    assert tenant is not None
