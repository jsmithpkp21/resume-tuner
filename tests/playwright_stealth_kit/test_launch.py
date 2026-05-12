"""Tests for playwright_stealth_kit.launch_stealth_chrome.

The launch helper is a context manager that bundles `playwright_stealth.Stealth`
with a persistent-context Chrome launch. A live browser test requires:

- system Chrome installed (channel='chrome'); the test skips otherwise
- ~5s per browser spin-up
- `headless=True` so it can run in CI without a display server. (Real usage
  runs headed; the stealth check we care about — `navigator.webdriver` — is
  applied identically in either mode.)

That makes the live test heavier than the default `make test` path, so it
is marked `slow` (skips by default; runs explicitly via `pytest -m slow`).

The light tests cover the public-API surface (imports + docstring contract +
exported defaults) and DO NOT require Playwright to be installed — they
exercise the kit's lazy-import design (`import playwright_stealth_kit`
succeeds without Playwright; only the helper call needs it). The slow test
is the one that requires Playwright + Chrome and uses `importorskip` /
`shutil.which` to skip cleanly in environments without them.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def test_launch_helper_is_importable_and_documented() -> None:
    """The public API surface (`launch_stealth_chrome`) is exported and the
    realistic-expectations callout (stealth scope + Workday/Google SSO
    caveats) is enforced in the docstring.

    Locks the contract so a future refactor can't rename/hide the helper or
    silently strip the realistic-expectations callout that PR #324 / issue
    #323 review rounds insisted on.

    This test deliberately does NOT trigger the lazy Playwright imports —
    `import playwright_stealth_kit` works in venvs without Playwright,
    and verifying that property is part of the contract.
    """
    from playwright_stealth_kit import launch_stealth_chrome

    assert callable(launch_stealth_chrome)
    doc = (
        (launch_stealth_chrome.__doc__ or "")
        + "\n"
        + (
            __import__("playwright_stealth_kit.launch", fromlist=["launch"]).__doc__
            or ""
        )
    )
    doc_l = doc.lower()
    # Core capability claims:
    assert "stealth" in doc_l
    assert "persistent" in doc_l
    # Realistic-expectations callout (the part Copilot kept catching as
    # docstring drift during review):
    assert "workday" in doc_l
    assert "google" in doc_l, "Google SSO refusal caveat must remain in docstring"


def test_launch_helper_exposes_defaults() -> None:
    """Kit-level constants are importable for callers that need a non-persistent
    variant (test_stealth.py) but want the same launch args + viewport defaults.

    Like the docstring test, this does not trigger any Playwright import.
    """
    from playwright_stealth_kit.launch import DEFAULT_LAUNCH_ARGS, DEFAULT_VIEWPORT

    assert DEFAULT_VIEWPORT == {"width": 1280, "height": 900}
    assert "--disable-popup-blocking" in DEFAULT_LAUNCH_ARGS


@pytest.mark.slow
def test_launch_stealth_chrome_actually_launches_with_stealth_applied(
    tmp_path: Path,
) -> None:
    """Live test: spin up Chrome via the kit, verify navigator.webdriver is
    patched (the canonical stealth signal). Marked `slow` because it actually
    boots Chrome.

    `importorskip` lives inside this test (not at module scope) so the light
    tests above keep running in environments without the Playwright layer
    installed — which is the default in CI.
    """
    import shutil

    pytest.importorskip("playwright_stealth")
    pytest.importorskip("playwright.sync_api")

    # launch_stealth_chrome defaults to channel='chrome' (Google Chrome).
    # `chromium` alone is not sufficient — we'd just fail at launch on a
    # system that has chromium-but-not-chrome. Skip cleanly instead.
    if not shutil.which("google-chrome"):
        pytest.skip("no Google Chrome available (kit defaults to channel='chrome')")

    from playwright_stealth_kit import launch_stealth_chrome

    user_data_dir = tmp_path / "stealth-test-profile"
    with launch_stealth_chrome(
        user_data_dir=user_data_dir,
        headless=True,  # CI-friendly; real usage runs headed
    ) as context:
        page = context.pages[0] if context.pages else context.new_page()
        # Real navigation rather than about:blank — stealth's init scripts
        # don't always apply to about:blank in persistent-context+headless.
        page.goto("https://example.com", wait_until="domcontentloaded", timeout=10000)
        webdriver_flag = page.evaluate("() => navigator.webdriver")
        # With stealth: navigator.webdriver should be false (or undefined).
        # Without stealth: it would be true.
        assert webdriver_flag is False or webdriver_flag is None, (
            f"stealth did not patch navigator.webdriver "
            f"(got {webdriver_flag!r}) — kit launch may be broken"
        )
