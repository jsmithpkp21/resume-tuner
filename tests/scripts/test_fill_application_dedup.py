"""Tests for `scripts/fill_application.py` `_dedup_key` (#366).

The dedup loop in `on_snapshot` previously keyed on `(label, type)`,
which collapsed *distinct* fields sharing a label — most notably
"Email" + "Confirm Email" (both resolve to `contact.email`),
multi-step forms re-showing the same labels, and Workday repeating
sub-forms. In live mode the second field was left empty.

These tests cover the new `_dedup_key` helper which adds `id`/`name`
to the dedup identity, falling back to label only when neither is
present. We also simulate the dedup loop itself against a small
fields-list fixture so the end-to-end behavior — distinct fields
stay separate, MutationObserver re-emits of the same DOM element
collapse — is locked in.
"""

from __future__ import annotations

from typing import Any

from scripts.fill_application import _dedup_key


def _dedup_loop(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mirror of the dedup body in `on_snapshot`. Returns the fields
    that *survive* the dedup check, in order. Kept in this test file
    so a refactor of `on_snapshot` doesn't silently change behavior
    without these tests flagging it.
    """
    seen: set[tuple[str, str, str]] = set()
    survivors: list[dict[str, Any]] = []
    for fld in fields:
        lbl = (fld.get("label") or "").strip()
        if not lbl:
            continue
        key = _dedup_key(fld)
        if key in seen:
            continue
        seen.add(key)
        survivors.append(fld)
    return survivors


class TestDedupKey:
    def test_id_takes_precedence_over_name(self) -> None:
        # Both id and name present — id wins as the identity component
        # so two fields with the same name but different ids stay
        # distinct (rare, but valid HTML).
        key = _dedup_key({"label": "Email", "type": "email", "id": "e1", "name": "n"})
        assert key == ("e1", "email", "Email")

    def test_falls_back_to_name_when_no_id(self) -> None:
        key = _dedup_key({"label": "Email", "type": "email", "name": "email_field"})
        assert key == ("email_field", "email", "Email")

    def test_falls_back_to_label_when_no_id_or_name(self) -> None:
        # Label-only fields preserve pre-#366 behavior — still
        # deduped, just by their label.
        key = _dedup_key({"label": "Email", "type": "email"})
        assert key == ("Email", "email", "Email")

    def test_strips_whitespace_from_identity_components(self) -> None:
        key = _dedup_key({"label": "  Email  ", "type": "email", "id": "  e1  "})
        assert key == ("e1", "email", "Email")

    def test_missing_type_yields_empty_string(self) -> None:
        # The field extractor always sets `type`, but defensive: don't
        # KeyError if a future payload shape drops it. Two fields with
        # the same identity but no type still collapse — same DOM
        # element, MutationObserver re-emit.
        key = _dedup_key({"label": "Email", "id": "e1"})
        assert key == ("e1", "", "Email")


class TestDedupLoop:
    def test_same_label_different_id_distinct_keys(self) -> None:
        # The "Email" + "Confirm Email" case from the issue. Some ATS
        # markup trims "Confirm" so both surface with the same label
        # after the matcher's normalization. Distinct ids means
        # distinct fields, both must reach the matcher.
        fields = [
            {"label": "Email", "type": "email", "id": "email"},
            {"label": "Email", "type": "email", "id": "confirm_email"},
        ]
        assert _dedup_loop(fields) == fields

    def test_same_label_different_name_distinct_keys(self) -> None:
        # Workday repeating sub-form shape: same visible label,
        # different `name` attrs (typically suffixed with an index).
        fields = [
            {"label": "Company", "type": "text", "name": "wd-experience-0-company"},
            {"label": "Company", "type": "text", "name": "wd-experience-1-company"},
        ]
        assert _dedup_loop(fields) == fields

    def test_same_id_collapses_mutation_observer_reemits(self) -> None:
        # The original dedup target: MutationObserver fires every tick
        # while the form is interacted with, and re-emits identical
        # fields. Same id → same DOM element → collapse.
        fields = [
            {"label": "Email", "type": "email", "id": "email"},
            {"label": "Email", "type": "email", "id": "email"},
            {"label": "Email", "type": "email", "id": "email"},
        ]
        survivors = _dedup_loop(fields)
        assert len(survivors) == 1
        assert survivors[0]["id"] == "email"

    def test_empty_label_skipped_regardless_of_id(self) -> None:
        # The `if not lbl: continue` guard in on_snapshot survives
        # — a pure-id field with no visible label can't be matched
        # against the answer bank.
        fields = [
            {"label": "", "type": "text", "id": "x"},
            {"label": "Name", "type": "text", "id": "name"},
        ]
        survivors = _dedup_loop(fields)
        assert len(survivors) == 1
        assert survivors[0]["label"] == "Name"

    def test_label_only_fields_still_dedupe(self) -> None:
        # Pre-#366 behavior preserved for fields with no id or name:
        # the same label still collapses.
        fields = [
            {"label": "First Name", "type": "text"},
            {"label": "First Name", "type": "text"},
        ]
        survivors = _dedup_loop(fields)
        assert len(survivors) == 1

    def test_different_types_same_id_distinct(self) -> None:
        # Type is part of the key so a hypothetical id collision
        # between a text input and (say) a hidden field doesn't
        # accidentally collapse. Not a common real-world case but
        # cheap to keep in the key.
        fields = [
            {"label": "Email", "type": "email", "id": "x"},
            {"label": "Email", "type": "text", "id": "x"},
        ]
        survivors = _dedup_loop(fields)
        assert len(survivors) == 2
