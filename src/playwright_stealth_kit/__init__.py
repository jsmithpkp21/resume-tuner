"""playwright_stealth_kit — Playwright + stealth + Chrome launch harness.

Bundles the boilerplate for a stealth-wrapped, persistent-profile Chrome
session: `playwright_stealth.Stealth` applied to the Playwright instance,
persistent context via `launch_persistent_context()` against the system
Chrome (channel='chrome'), popup blocker disabled (so Workday's "Sign in
with Google" SSO popup actually opens), reasonable viewport defaults.

The kit is intentionally a thin sibling to `resume_builder` — it has no
job-application-specific logic. The intent is that this directory eventually
extracts to its own repo (`git filter-repo --subdirectory-filter
src/playwright_stealth_kit`) once a second consumer materializes outside
the resume-builder use case.

See issue #323 for the integration design and observed stealth behavior
against real ATS sites (Akamai/Workable: passes; Google SSO: still
refused — fall back to email+password).
"""

from .launch import launch_stealth_chrome

__all__ = ["launch_stealth_chrome"]
