"""Python wrapper for the DOM-walking field-extraction JS.

The JS itself lives alongside this module as `field_extractor.js`. It is
injected into every page Playwright loads via `context.add_init_script(...)`;
the script walks all form fields (incl. shadow-root contents — Workday is
mostly custom elements with shadow DOMs), debounces on DOM stability, and
calls `window.__claudePush(payload)` with a structured snapshot
(`{url, ts, fields: [{label, type, required, options, name, id, ...}]}`).

The Python wrapper exposes the JS contents as the `EXTRACTOR_JS` module
constant for direct injection, and provides `load_extractor_js()` for
callers that want to reload it (e.g. tests that mutate and restore).

Resource location uses `importlib.resources` so the JS asset travels
correctly with `pip install` / wheel builds (paired with the
`[tool.setuptools.package-data]` config in `.pyproject.meta.toml`).
"""

from __future__ import annotations

from importlib import resources

_PACKAGE = __name__.rsplit(".", 1)[0]  # "job_apply_kit"


def load_extractor_js() -> str:
    """Read and return the extractor JS source.

    Most callers should just use the module-level `EXTRACTOR_JS` constant.
    This function is for callers that need to re-read the file (e.g. tests
    that overwrite it temporarily, or hot-reload scenarios). Backed by
    `importlib.resources` so it works in zipped/installed wheels too,
    not just source layouts.
    """
    return (
        resources.files(_PACKAGE)
        .joinpath("field_extractor.js")
        .read_text(encoding="utf-8")
    )


EXTRACTOR_JS: str = load_extractor_js()
