"""Display-safe value redaction for the application-submission flow.

Pure functions, no I/O, no Playwright. Lives in `job_apply_kit/`
rather than `scripts/fill_application.py` so tests can import the
helpers without dragging in `fill_application.py`'s top-level
Playwright imports (which sys.exit(2) when Playwright isn't
installed — see `feedback_module_import_sys_exit_traps_tests`).

Two callers as of this writing:

  - `scripts/fill_application.py` — redacts answer-bank values in
    the success-path display and error-path messages (#364, #365).
  - tests verifying the privacy contract.
"""

from __future__ import annotations


def redact(value: str) -> str:
    """Display-safe value fingerprint: never leaks contents, but
    still distinguishes different values via their length."""
    return f"<value len={len(value)}>"


def redact_error_text(text: str, sensitive: str | None) -> str:
    """Substring-replace `sensitive` (if any) with `redact(sensitive)`
    wherever it appears in `text`.

    Used on error messages from `fill_application._perform_live_fill`
    (#365). Playwright exceptions can embed the value the matcher
    attempted to fill into the error string; if we hand that text to
    the `[fill-error]` log line or persist it to the fill-decisions
    JSON, the value leaks regardless of `--show-values`. This helper
    makes the redaction posture consistent with the success-path
    display.
    """
    if sensitive:
        text = text.replace(sensitive, redact(sensitive))
    return text
