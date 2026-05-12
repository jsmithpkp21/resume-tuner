"""Stealth-wrapped Chrome launch helper.

`launch_stealth_chrome()` returns a context manager that:

1. Applies `playwright_stealth.Stealth` to the Playwright instance (patches
   `navigator.webdriver`, plugin lists, language ordering, WebGL vendor,
   user-agent's `Headless` suffix, sec-ch-ua, and a half-dozen smaller
   automation tells on every page).
2. Launches Google Chrome via `channel='chrome'` with a persistent user-data
   directory (so cookies, logins, and session state survive across runs).
3. Disables the popup blocker (Workday "Sign in with Google" opens SSO in
   a popup that Playwright Chromium blocks by default).
4. Yields the live `BrowserContext` for the caller to drive.

On exit (normal or exception), the context is closed best-effort; the
Playwright manager handles its own lifecycle.

Realistic expectations on what stealth fixes (and doesn't), measured
empirically and tracked in issue #323:
  - ✓ Sannysoft canary (the classic 20-signal grid)
  - ✓ Akamai Bot Manager (Workday tenants behind it)
  - ✓ Workable mid-flow fingerprinting (expected — untested live post-stealth)
  - ✗ Google SSO — still refuses Playwright-launched sessions. Fall back
       to email+password account creation in-session for Workday tenants.

(Additional consumer-side notes — per-submission captures, ATS-specific
quirks, etc. — live in resume-builder's local-only `data/applications/`
research dir which is gitignored. Issue #323 is the canonical reference.)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext

# Note: `playwright` and `playwright_stealth` are imported lazily inside
# launch_stealth_chrome() so `import playwright_stealth_kit` succeeds in
# environments that haven't installed the optional Playwright layer
# (e.g. fresh consumer venvs where Playwright is gated on
# RESUME_BUILDER_ENABLE_PLAYWRIGHT). Callers that actually invoke the
# helper get a clear ImportError pointing at the install command.

DEFAULT_VIEWPORT: dict[str, int] = {"width": 1280, "height": 900}
DEFAULT_CHANNEL: str = "chrome"
DEFAULT_LAUNCH_ARGS: tuple[str, ...] = (
    # Workday's "Sign in with Google" SSO opens in a popup; Playwright's
    # default popup blocker rejects it. Disable so SSO at least gets a chance
    # (Google still fingerprints; see PHASE_2_FINDINGS.md).
    "--disable-popup-blocking",
)


@contextmanager
def launch_stealth_chrome(
    *,
    user_data_dir: Path | str,
    viewport: dict[str, int] | None = None,
    channel: str = DEFAULT_CHANNEL,
    headless: bool = False,
    accept_downloads: bool = True,
    extra_args: tuple[str, ...] = (),
) -> Iterator[BrowserContext]:
    """Yield a stealth-applied, persistent-profile Chromium context.

    Parameters
    ----------
    user_data_dir:
        On-disk path for Chrome's persistent profile. Cookies, logins,
        local storage, etc. survive across runs. Must be writable.
    viewport:
        Initial viewport. Default: 1280×900 — large enough for most ATS
        flows without scrollbars.
    channel:
        Playwright launch channel. Default: `'chrome'` — uses the
        system-installed Google Chrome (Ubuntu 26.04 has no bundled
        Chromium binary for Playwright). Pass `''` (empty) to let
        Playwright choose its bundled Chromium when available.
    headless:
        Default `False` — most real-site fingerprint checks fail in
        headless mode regardless of stealth.
    accept_downloads:
        Default `True` — apply flows often offer to download a confirmation
        PDF after submit.
    extra_args:
        Additional Chrome args appended to the defaults
        (`--disable-popup-blocking`).

    Yields
    ------
    BrowserContext
        The persistent-context handle. Use `context.new_page()` or
        `context.pages[0]` to start driving.

    Notes
    -----
    - The context is closed on exit (best-effort; closing fails silently
      if the browser is already gone, e.g. user closed the window).
    - For tracing, call `context.tracing.start(...)` after entering.
    - Stealth is applied to every page in the context (including new
      tabs and SSO popups) — no per-page work needed by the caller.
    """
    # Lazy imports so `import playwright_stealth_kit` succeeds in venvs
    # without the optional Playwright layer; only fails on actual use.
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError as e:
        raise ImportError(
            "playwright and/or playwright-stealth are required to call "
            "launch_stealth_chrome(). Install: "
            "pip install playwright playwright-stealth"
        ) from e

    launch_kwargs: dict[str, Any] = {
        "user_data_dir": str(user_data_dir),
        "headless": headless,
        "viewport": viewport or dict(DEFAULT_VIEWPORT),
        "accept_downloads": accept_downloads,
        "args": list(DEFAULT_LAUNCH_ARGS + tuple(extra_args)),
    }
    if channel:
        launch_kwargs["channel"] = channel

    stealth = Stealth()
    # stealth.use_sync wraps the Playwright manager for new_page-style flows,
    # but `launch_persistent_context()` creates contexts that bypass the
    # patched path. Calling apply_stealth_sync explicitly on the persistent
    # context ensures every page in it gets the patches (verified empirically
    # against navigator.webdriver in tests/playwright_stealth_kit/).
    with stealth.use_sync(sync_playwright()) as p:
        context = p.chromium.launch_persistent_context(**launch_kwargs)
        stealth.apply_stealth_sync(context)
        try:
            yield context
        finally:
            # Browser may already be gone (user closed window mid-session);
            # close failure is expected and harmless in that case.
            with suppress(Exception):
                context.close()
