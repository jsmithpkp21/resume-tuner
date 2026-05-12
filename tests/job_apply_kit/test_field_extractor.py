"""Privacy regression tests for `job_apply_kit.field_extractor` (#351).

The DOM walker in `field_extractor.js` is injected into every page in a
recording session and pushes per-field snapshots back to the Python
driver. Before #351 it emitted the live `value` of every input,
textarea, contenteditable, and combobox, plus the current `checked` /
`selected` flag on every radio / select option. That meant capture
files could persist cleartext passwords, SSNs, 2FA codes, and the
user's EEO / veteran / disability selections.

These tests are deliberately string-based — fragile but cheap — so a
future edit that re-introduces value/innerText/checked/selected
emission fails immediately rather than silently shipping a regression.

JS line comments are stripped before searching so the explanatory
comments in the source (which legitimately reference the omitted
fields by name) don't trip the assertions.
"""

from __future__ import annotations

import re

from job_apply_kit import EXTRACTOR_JS


def _strip_js_line_comments(src: str) -> str:
    """Remove `//` line comments. The extractor uses only line-comments,
    no `/* */` blocks. Quoted strings in this file never contain `//`,
    so a naive line-by-line strip is safe here."""
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


_CODE = _strip_js_line_comments(EXTRACTOR_JS)


class TestExtractorDoesNotEmitUserInput:
    """The extractor must not emit `value` / `innerText` for the main
    field-push path (inputs, textareas, contenteditable, comboboxes).
    """

    def test_no_el_value_read(self) -> None:
        # The pre-#351 line was:
        #   value: el.value !== undefined ? el.value : (el.innerText || '').slice(0, 500),
        # Any reintroduction of `el.value` in the emitted payload should
        # trip this assertion.
        assert "el.value" not in _CODE, (
            "field_extractor.js must not read user-typed `el.value` — #351"
        )

    def test_no_innertext_fallback_on_field_element(self) -> None:
        # The pre-#351 fallback was `(el.innerText || '').slice(0, 500)`
        # for contenteditable, where `el` is the form field. Other
        # `innerText` reads in labelOf() are scoped to `<label>` / parent
        # elements (form-author-supplied label text, not user input),
        # so this check targets the specific `el.innerText` pattern.
        assert "el.innerText" not in _CODE, (
            "field_extractor.js must not read user-typed `el.innerText` — #351"
        )


class TestExtractorDoesNotEmitUserSelection:
    """For radio + select options, the form-author-supplied `value` and
    `label` are page content and safe to emit; the user's current
    `checked` / `selected` flag reveals their choice and is omitted.
    """

    def test_no_radio_checked_flag(self) -> None:
        # Pre-#351 radio option emission included `checked: !!r.checked`.
        assert "r.checked" not in _CODE, (
            "field_extractor.js must not emit radio `r.checked` — #351"
        )

    def test_no_select_selected_flag(self) -> None:
        # Pre-#351 select option emission included `selected: o.selected`.
        assert "o.selected" not in _CODE, (
            "field_extractor.js must not emit select `o.selected` — #351"
        )


class TestExtractorStillEmitsStructuralMetadata:
    """Negative tests above don't prove the extractor still works.
    Sanity-check that the structural fields the matcher depends on
    (`label`, `type`, `options`) are still present in the source.
    """

    def test_emits_label(self) -> None:
        assert "label:" in _CODE

    def test_emits_type(self) -> None:
        assert "type:" in _CODE

    def test_emits_options(self) -> None:
        # Both radio groups and selects push an `options` array.
        assert "options:" in _CODE
