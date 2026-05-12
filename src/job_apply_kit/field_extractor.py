"""Python wrapper for the DOM-walking field-extraction JS.

The JS itself lives alongside this module in `field_extractor.js`. It is
injected into every page Playwright loads via `context.add_init_script(...)`;
the script walks all form fields (incl. shadow-root contents — Workday is
mostly custom elements with shadow DOMs), debounces on DOM stability, and
calls `window.__claudePush(payload)` with a structured snapshot
(`{url, ts, fields: [{label, type, required, options, name, id, ...}]}`).

The Python wrapper exposes the JS contents as the `EXTRACTOR_JS` module
constant for direct injection, and provides `load_extractor_js()` for
callers that want to reload it (e.g. tests that mutate and restore).
"""

from __future__ import annotations

from pathlib import Path

_EXTRACTOR_PATH = Path(__file__).parent / "field_extractor.js"


def load_extractor_js() -> str:
    """Read and return the extractor JS source.

    Most callers should just use the module-level `EXTRACTOR_JS` constant.
    This function is for callers that need to re-read the file (e.g. tests
    that overwrite it temporarily, or hot-reload scenarios).
    """
    return _EXTRACTOR_PATH.read_text(encoding="utf-8")


EXTRACTOR_JS: str = load_extractor_js()
