"""URL → (ATS family, tenant) inference for the credential-lookup hook.

Used by `scripts/fill_application.py` to derive the `(ats, tenant)`
pair passed to `resume_builder.credential_store.lookup` / `.record`
when a password field is matched. Independent of `jd_ingest.py`'s
job-board parsing — that module has IP/host blocklists and content
fetching that aren't needed for a pure-URL family classifier.

Supported families:

  - `workday`   — `*.myworkdayjobs.com`, `*.wd1.myworkdayjobs.com`,
                  `*.workdayjobs.com`. Tenant = leftmost subdomain
                  before the workday host suffix (e.g.
                  `becu.wd1.myworkdayjobs.com` → `becu`).
  - `workable`  — `apply.workable.com/<tenant>/...`. Tenant = first
                  non-empty path segment.
  - `greenhouse` — `boards.greenhouse.io/<tenant>/...` and
                  `job-boards.greenhouse.io/<tenant>/...`. Tenant =
                  first non-empty path segment.
  - `icims`     — `*.icims.com`. Tenant = leftmost subdomain (e.g.
                  `careers-acme.icims.com` → `careers-acme`).

For everything else the function returns `(None, None)` — callers
should prompt the user for the values manually.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Hostname → ATS family suffix maps. Each tuple is matched as a
# "host ends with .<suffix>" check, so a literal "apply.workable.com"
# entry is fine for exact-match families too.
_WORKDAY_SUFFIXES: tuple[str, ...] = (
    "myworkdayjobs.com",
    "workdayjobs.com",
)
_GREENHOUSE_HOSTS: tuple[str, ...] = (
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
)
_WORKABLE_HOSTS: tuple[str, ...] = ("apply.workable.com",)
_ICIMS_SUFFIX: str = "icims.com"


def _host_of(url: str) -> str:
    """Lowercase hostname from a URL, stripping port + trailing dot."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    return host


def _path_segments(url: str) -> list[str]:
    """Non-empty path segments from a URL, preserving order."""
    parsed = urlparse(url)
    return [seg for seg in parsed.path.split("/") if seg.strip()]


def _leftmost_label_before_suffix(host: str, suffix: str) -> str | None:
    """Return the leftmost DNS label of `host` after stripping the
    `.{suffix}` portion. Returns None if `host` doesn't end with the
    suffix or there are no labels left.

    Examples:
        ("becu.wd1.myworkdayjobs.com", "myworkdayjobs.com") -> "becu"
        ("careers-acme.icims.com",     "icims.com")          -> "careers-acme"
        ("myworkdayjobs.com",          "myworkdayjobs.com") -> None
    """
    if not host.endswith("." + suffix):
        return None
    prefix = host[: -(len(suffix) + 1)]
    labels = [label for label in prefix.split(".") if label]
    if not labels:
        return None
    return labels[0]


def infer_ats_tenant(url: str) -> tuple[str | None, str | None]:
    """Classify a URL into `(ats_family, tenant)`.

    Args:
        url: The page URL the user is currently on (typically from
            `payload.get("url")` in `fill_application.on_snapshot`).

    Returns:
        `(ats_family, tenant)` where `ats_family` is one of
        `"workday" | "workable" | "greenhouse" | "icims"` and `tenant`
        is the lowercased slug extracted per family. Returns
        `(None, None)` when the URL doesn't match any supported family
        or when the tenant slug can't be derived (e.g. apex domain hit,
        or empty path on a path-slug host).
    """
    if not url:
        return (None, None)
    host = _host_of(url)
    if not host:
        return (None, None)

    # Workday — subdomain-based tenant on the workday host suffixes.
    for suffix in _WORKDAY_SUFFIXES:
        tenant = _leftmost_label_before_suffix(host, suffix)
        if tenant:
            return ("workday", tenant)

    # iCIMS — same shape, different suffix.
    tenant = _leftmost_label_before_suffix(host, _ICIMS_SUFFIX)
    if tenant:
        return ("icims", tenant)

    # Workable + Greenhouse — exact-host with path-slug tenant.
    if host in _WORKABLE_HOSTS:
        segs = _path_segments(url)
        if segs:
            return ("workable", segs[0].lower())
        return (None, None)

    if host in _GREENHOUSE_HOSTS:
        segs = _path_segments(url)
        if segs:
            return ("greenhouse", segs[0].lower())
        return (None, None)

    return (None, None)
