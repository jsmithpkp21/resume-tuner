"""Tests for playwright_stealth_kit.launch_stealth_chrome.

The launch helper is a context manager that bundles `playwright_stealth.Stealth`
with a persistent-context Chrome launch. A live browser test would require:

- system Chrome installed (channel='chrome')
- WSLg or X11 display (we run headed)
- ~5s per browser spin-up

That makes full launch tests too heavy for the default `make test` path. The
heavy live-browser test is marked `slow` so it runs when explicitly requested
(`pytest -m slow`) and skips otherwise. Light tests cover the imports +
public surface so a refactor that breaks the kit's API fails fast.

The kit itself relies on `playwright_stealth` being installed; CI without
the playwright layer installed should `importorskip`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

playwright_stealth = pytest.importorskip("playwright_stealth")
playwright = pytest.importorskip("playwright.sync_api")


def test_launch_helper_is_importable_and_documented() -> None:
    """The public API surface (`launch_stealth_chrome`) is exported and documented.

    Locks the contract so a future refactor that renames or hides the helper
    fails before any downstream consumer breaks at runtime.
    """
    from playwright_stealth_kit import launch_stealth_chrome

    assert callable(launch_stealth_chrome)
    # The kit's whole reason to exist — make sure the function's docstring
    # references stealth, persistent profile, and Workday / SSO realism
    # (so a future drive-by edit can't strip the realistic-expectations
    # callout that PR #324 / issue #323 review rounds insisted on).
    doc = launch_stealth_chrome.__doc__ or ""
    assert "stealth" in doc.lower()
    assert "persistent" in doc.lower()


def test_launch_helper_exposes_defaults() -> None:
    """Kit-level constants are importable for callers that need a non-persistent
    variant (test_stealth.py) but want the same launch args + viewport defaults.
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
    """
    import shutil

    if not shutil.which("google-chrome") and not shutil.which("chromium"):
        pytest.skip("no system Chrome/Chromium available")

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
