#!/usr/bin/env python3
"""Playwright-driven semi-auto filler — dry-run (#319) + live (#363).

Opens Chrome via the same stealth-wrapped persistent context as
`scripts/record_application.py`, injects the field extractor, and on each
stable snapshot runs `job_apply_kit.label_matcher.match` per field.

Two modes:

  - **Dry-run** (default): LOGS what it would fill but never modifies
    the DOM. Use this to validate the matcher against a real apply
    page, spot missing synonyms, catch new honeypot patterns.
  - **Live** (`--live`): actually fills matched fields via
    `Locator.press_sequentially` / `Locator.select_option` /
    `Locator.check`. Honeypots,
    `[account]` passwords (handed to the credential hook — #341), and
    `[work_experience]` (Phase 3-C scope) are NEVER autofilled
    regardless of flags. Sensitive bank sections (eeo, consent,
    preferences, …) require explicit opt-in via `--fill-sections`.
    Submit / Next / Apply buttons are never clicked — user reviews +
    submits manually.

Per-role Workday loop handling is a future sub-issue (Phase 3-C).

Usage (dry-run):

    scripts/fill_application.py <apply-url> \\
        --bank data/applications/_answer_bank.toml

Usage (live, with broader section scope):

    scripts/fill_application.py <apply-url> \\
        --bank data/applications/_answer_bank.toml \\
        --live --fill-sections name,contact,address,links,education,eeo \\
        --type-delay-ms 80-180 --confirm-before-fill

Outputs (under <capture-dir>):
    fill-decisions-<slug>-<ts>.json  per-field decision log (atomic write)
    trace-<slug>-<ts>/               chunked Playwright traces

Privacy:
  - Match values are **redacted by default** (the answer bank is PII +
    can hold per-ATS passwords). Terminal output shows the resolved
    section/sub_key, plus a short fingerprint (`<value len=N>`) so you
    can tell different values apart without leaking them.
  - Pass `--show-values` to print the actual filled value (local debug only).
  - The fill-decisions JSON ALWAYS redacts values unless `--show-values`
    is set, so capture archives are safe to share.
  - Scope: `--show-values` controls only the **answer-bank-derived**
    display path. The injected field extractor (#351) never captures
    user-typed input contents from the live page, so there is no
    "show user-typed values" knob — that data simply isn't collected.
  - Credential-store integration (#341): when the matcher hits a
    field in `[account]` that resolves to `password_lookup_path`,
    the script calls `job_apply_kit.handle_credential_match` with the
    page URL. The hook either prints the saved
    `resume_builder.credential_store` entry for the inferred
    `(ats, tenant)` (display-only — user types) or prompts and
    persists a new credential. The password is **always** redacted in
    the fill-decisions JSON (replaced with a `<credential-store:
    ats.tenant>` placeholder) regardless of `--show-values`.

Safety:
  - `--slug` is validated against `[A-Za-z0-9_-]` to prevent path-escape.
  - `--bank`, `--profile-dir`, `--capture-dir` are checked against the
    repo's blocked-runtime-roots policy before any filesystem I/O.
"""

from __future__ import annotations

import argparse
import getpass
import random
import sys
import time
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from playwright.sync_api import Locator
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from job_apply_kit import (
        EXTRACTOR_JS,
        Match,
        Skip,
        atomic_write_json,
        decide_fill,
        handle_credential_match,
        infer_ats_tenant,
        match,
        parse_type_delay_range,
        pick_typing_delay,
        sanitize_slug,
    )
    from playwright_stealth_kit import launch_stealth_chrome
    from resume_builder._runtime_guard import assert_not_blocked_runtime_input
except ModuleNotFoundError as e:
    # Only treat the optional 3rd-party deps as install-hints. Local-package
    # ModuleNotFoundError (job_apply_kit / playwright_stealth_kit /
    # resume_builder) means the editable install is broken — surface the
    # real traceback instead of telling the user to "pip install playwright".
    top = (e.name or "").split(".", 1)[0]
    if top in {"playwright", "playwright_stealth"}:
        sys.stderr.write(
            f"missing {top}. Install with:\n"
            "  pip install playwright playwright-stealth\n"
        )
        sys.exit(2)
    raise


DEFAULT_PROFILE_DIR = Path("data/applications/.browser-profile")
DEFAULT_CAPTURE_DIR = Path("data/applications/_capture")
CHUNK_INTERVAL_S = 20

# Default --fill-sections whitelist when --live is on but the user
# didn't pass --fill-sections explicitly. Sensitive bank sections
# (eeo / consent / preferences / referral / profile_fields) require
# explicit opt-in; this default covers the high-fill / low-risk
# identity sections.
DEFAULT_FILL_SECTIONS = "name,contact,address,links,education"
DEFAULT_TYPE_DELAY_MS = "50-150"


def _redact(value: str) -> str:
    """Display-safe value fingerprint: never leaks contents, but still
    distinguishes different values via their length."""
    return f"<value len={len(value)}>"


class _TerminalPrompter:
    """Production `CredentialPrompter` — wraps `input()` and
    `getpass.getpass()`. The credential hook in `job_apply_kit`
    accepts any object with `ask(prompt)` / `ask_secret(prompt)`, so
    tests inject canned-response fakes; this is the real one."""

    def ask(self, prompt: str) -> str:
        return input(prompt)

    def ask_secret(self, prompt: str) -> str:
        return getpass.getpass(prompt)


def _decision_summary(decisions: list[dict[str, Any]]) -> dict[str, int]:
    """Per-bucket counts for the run summary.

    Buckets:

      - ``filled`` / ``fill-error`` — live-mode DOM action outcomes.
      - ``match[<decision>]`` — Match that didn't fill, bucketed by the
        gate decision (``skip-dry-run`` / ``skip-section-gated`` /
        ``skip-account`` / ``skip-work-experience`` / ``skip-confirm-*``).
        Every Match entry has a ``decision`` field set by `on_snapshot`,
        so a plain ``match`` bucket should never appear in practice.
      - ``skip[<reason>]`` — Skip from the matcher (honeypot, no-match,
        empty-value, unresolved-sub-key, intentional-skip).
    """
    out: dict[str, int] = {}
    for d in decisions:
        k = d["outcome"]
        if "reason" in d:
            # Skip entry from the matcher.
            k = f"skip[{d['reason']}]"
        elif k == "match" and "decision" in d:
            k = f"match[{d['decision']}]"
        out[k] = out.get(k, 0) + 1
    return out


def _dedup_key(fld: dict[str, Any]) -> tuple[str, str, str]:
    """Stable dedup identity for a snapshot field.

    The MutationObserver re-emits the same DOM element on every tick, so
    `on_snapshot` needs to skip fields it has already processed. But the
    earlier key `(label, type)` collapsed *distinct* fields that share a
    label/type — "Email" + "Confirm Email" (matcher resolves both to
    `contact.email`), repeated labels across multi-step forms, Workday
    repeating sub-forms — leaving the second field empty in live mode.

    Key the dedup on the field's own `id` / `name` (which uniquely
    identify a DOM element), falling back to the visible label only
    when neither is present. `label` and `type` remain in the tuple so
    edge cases like two shadow-DOM nodes with the same `id` but different
    visible labels still distinguish.
    """
    lbl = (fld.get("label") or "").strip()
    ftype = fld.get("type", "")
    fid = (fld.get("id") or "").strip()
    name = (fld.get("name") or "").strip()
    identity = fid or name or lbl
    return (identity, ftype, lbl)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="apply URL to open")
    parser.add_argument(
        "--bank",
        type=Path,
        required=True,
        help="path to the answer-bank TOML (e.g. data/applications/_answer_bank.toml)",
    )
    parser.add_argument(
        "--slug",
        default=None,
        help=(
            "output filename slug (default: session-<ts>). Validation: must "
            "start with alphanumeric, only [A-Za-z0-9_-] thereafter, max 80 "
            "chars (sanitize_slug enforces this)."
        ),
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help=f"persistent Chrome profile dir (default: {DEFAULT_PROFILE_DIR})",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=DEFAULT_CAPTURE_DIR,
        help=f"output dir for traces + decisions JSON (default: {DEFAULT_CAPTURE_DIR})",
    )
    parser.add_argument(
        "--show-values",
        action="store_true",
        help=(
            "show actual answer-bank values in terminal + decisions JSON. "
            "Default redacts (the bank holds PII + per-ATS passwords)."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Actually fill matched fields via locator.press_sequentially "
            "/ select_option / check instead of dry-run logging. "
            "Honeypots, passwords, and work_experience are never filled "
            "regardless of this flag. Default: dry-run (Phase 3-A "
            "behavior unchanged)."
        ),
    )
    parser.add_argument(
        "--fill-sections",
        default=DEFAULT_FILL_SECTIONS,
        help=(
            "Comma-separated answer-bank sections this run may fill "
            f"when --live is set (default: {DEFAULT_FILL_SECTIONS}). "
            "Sensitive sections (eeo, consent, preferences, etc.) "
            "require explicit opt-in. Pass an empty string to "
            "section-gate everything."
        ),
    )
    parser.add_argument(
        "--type-delay-ms",
        type=parse_type_delay_range,
        default=parse_type_delay_range(DEFAULT_TYPE_DELAY_MS),
        # argparse calls `type=` on the user-supplied string; ValueError
        # from `parse_type_delay_range` is converted into a clean
        # "argument --type-delay-ms: invalid value" error automatically.
        help=(
            "Per-keystroke typing-delay jitter range in 'MIN-MAX' "
            f"format (default: {DEFAULT_TYPE_DELAY_MS}). Defends against "
            "zero-delay bot detection on Workday + similar ATSes."
        ),
    )
    parser.add_argument(
        "--confirm-before-fill",
        action="store_true",
        help=(
            "Pause and prompt before each live fill (y/n/skip). Useful "
            "the first time you run --live on a new ATS."
        ),
    )
    args = parser.parse_args(argv)

    # argparse already converted --type-delay-ms via parse_type_delay_range.
    type_delay_range = args.type_delay_ms
    # Tokenize --fill-sections into a frozenset. Empty entries from
    # consecutive commas or leading/trailing commas are dropped so
    # `--fill-sections name,contact,` works.
    allowed_sections = frozenset(
        s.strip() for s in args.fill_sections.split(",") if s.strip()
    )
    typing_rng = random.Random()

    ts = int(time.time())
    slug = sanitize_slug(args.slug) if args.slug else f"session-{ts}"
    assert_not_blocked_runtime_input(args.bank)
    assert_not_blocked_runtime_input(args.profile_dir)
    assert_not_blocked_runtime_input(args.capture_dir)

    args.capture_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = args.capture_dir / f"trace-{slug}-{ts}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = args.capture_dir / f"fill-decisions-{slug}-{ts}.json"
    chunk_counter = [0]

    # Deterministic TOML parse (binary handle so tomllib doesn't depend on
    # OS-default text decoding).
    with args.bank.open("rb") as f:
        bank = tomllib.load(f)
    print(
        f"[setup] answer bank loaded: {len(bank)} sections, "
        f"{sum(len(v.get('synonyms', [])) for v in bank.values() if isinstance(v, dict))} synonyms"
    )
    if not args.show_values:
        print("[setup] PII redaction ON (values hidden; pass --show-values to disable)")

    # Per-field decisions accumulate here. Deduped by `_dedup_key`
    # — (id-or-name-or-label, type, label) — so MutationObserver
    # re-emits of the same DOM element collapse while two distinct
    # fields sharing a label (e.g. "Email" + "Confirm Email", Workday
    # repeating sub-forms) stay separate.
    decisions: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    # Per-session set of (ats, tenant) tuples we've already surfaced
    # a credential for — once the user has seen the banner they don't
    # need it repeated for every password / verify-password field on
    # the same page. Empty until the first account match fires.
    credential_seen: set[tuple[str, str]] = set()
    # Per-hostname cache of resolved (ats, tenant). Carries the
    # answer from the first hook call (which may have prompted for
    # ATS+tenant when inference failed) into later password fields
    # on the same host, so the user isn't asked again per field.
    host_ats_tenant_cache: dict[str, tuple[str, str]] = {}
    # Sections the user opted to skip mid-session via the
    # --confirm-before-fill prompt ("s" answer). Live mode honors
    # this in addition to the static --fill-sections whitelist.
    skip_sections_runtime: set[str] = set()
    # Holds the main Playwright Page once `with launch_stealth_chrome`
    # is entered. on_snapshot() is defined before that point but the
    # live-fill path needs a page reference; reading from a cell lets
    # us write once after launch without restructuring the closure.
    page_holder: list[Any] = [None]
    # Set by the --confirm-before-fill `q` answer. Checked by the
    # main wait_for_event loop so the session shuts down via the
    # existing close-handling path (predictable trace + decisions
    # flush) instead of raising KeyboardInterrupt inside a
    # Playwright-exposed callback, where exceptions don't surface
    # cleanly through the JS bridge.
    quit_requested: list[bool] = [False]
    prompter = _TerminalPrompter()

    def write_decisions() -> None:
        try:
            atomic_write_json(decisions_path, decisions)
        except OSError as e:
            print(f"  [warn] decisions write failed: {e}")

    def _resolve_locator(page: Any, fld: dict[str, Any]) -> Locator | None:
        """Try three locator strategies in priority order; return the
        first unique match (`count() == 1`). Returns None on no match,
        ambiguous match, or Playwright errors — caller logs and skips.
        """
        lbl = (fld.get("label") or "").strip()
        name = (fld.get("name") or "").strip()
        fid = (fld.get("id") or "").strip()
        candidates: list[Locator] = []
        if lbl:
            candidates.append(page.get_by_label(lbl, exact=True))
        if name:
            # CSS attribute selector with escaped value.
            safe = name.replace('"', '\\"')
            candidates.append(page.locator(f'[name="{safe}"]'))
        if fid:
            # Attribute selector instead of `#id`: valid HTML ids can
            # contain characters like `:` or `.` (common in Workday-
            # generated markup) that `#` selectors choke on.
            safe_id = fid.replace('"', '\\"')
            candidates.append(page.locator(f'[id="{safe_id}"]'))
        for loc in candidates:
            try:
                if loc.count() == 1:
                    return loc
            except Exception:
                continue
        return None

    def _perform_live_fill(
        page: Any,
        fld: dict[str, Any],
        m: Match,
    ) -> tuple[str, str]:
        """Execute the DOM action for a `fill` decision.

        Returns ("filled", "") on success or ("fill-error", reason)
        on any locator / action failure. Never raises — fill_application
        must survive single-field failures and continue the session.
        """
        loc = _resolve_locator(page, fld)
        if loc is None:
            return ("fill-error", "no unique locator")
        ftype = fld.get("type", "")
        value = m.value
        try:
            if ftype in (
                "text",
                "email",
                "tel",
                "url",
                "number",
                "search",
                "textarea",
                "contenteditable",
                "combobox",
                # `field_extractor.js` emits "textbox" for elements
                # with `role="textbox"` (custom rich-text components,
                # Workday's contenteditable wrappers). Same fill
                # semantics as a plain text input.
                "textbox",
            ):
                # Clear first — `press_sequentially` appends to existing
                # content, and ATS apply flows for logged-in users
                # often pre-populate fields (cached email, prior session
                # name). `fill("")` is the instant clear primitive; the
                # subsequent typed input still gets per-key delay.
                loc.fill("")
                delay = pick_typing_delay(type_delay_range, typing_rng)
                loc.press_sequentially(value, delay=delay)
            elif ftype == "select":
                # Try label-based selection first (matches what the user
                # sees), fall back to value-based.
                try:
                    loc.select_option(label=value)
                except Exception:
                    loc.select_option(value=value)
            elif ftype == "radio-group":
                # The locator we resolved is the group root; the actual
                # radio input lives under it with a specific [value=...].
                # The extractor emits `options` with each radio's value.
                opts = fld.get("options") or []
                target_val: str | None = None
                value_norm = value.strip().lower()
                for opt in opts:
                    olabel = str(opt.get("label", "")).strip().lower()
                    oval = str(opt.get("value", "")).strip()
                    if olabel == value_norm or oval.lower() == value_norm:
                        target_val = oval
                        break
                if target_val is None:
                    return ("fill-error", f"no radio option matched {value!r}")
                name = fld.get("name", "")
                if not name:
                    return ("fill-error", "radio-group missing name attr")
                safe_n = name.replace('"', '\\"')
                safe_v = target_val.replace('"', '\\"')
                page.locator(
                    f'input[type="radio"][name="{safe_n}"][value="{safe_v}"]'
                ).check()
            elif ftype == "checkbox":
                v = str(value).strip().lower()
                if v in ("true", "yes", "on", "1", "agree", "accept"):
                    loc.check()
                else:
                    loc.uncheck()
            else:
                return ("fill-error", f"unsupported field type {ftype!r}")
        except Exception as e:
            return ("fill-error", f"{type(e).__name__}: {e}")
        return ("filled", "")

    def on_snapshot(payload: dict[str, Any]) -> None:
        page_url = payload.get("url", "") or ""
        fields = payload.get("fields", [])
        new = 0
        for fld in fields:
            lbl = (fld.get("label") or "").strip()
            ftype = fld.get("type", "")
            if not lbl:
                continue
            key = _dedup_key(fld)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            d = match(lbl, bank)
            if isinstance(d, Match):
                # `decide_fill` is the single source of truth for what
                # to do with a Match. It encodes the
                # account.password_lookup_path → skip-account special-
                # case, the work_experience deferral, the honeypot
                # rail, the --live + --fill-sections gates, etc.
                # `on_snapshot` just routes on the returned decision.
                # Annotated `str` (not the narrower `FillDecision`
                # literal) because the confirm-before-fill branch can
                # overwrite the value with a runtime-only state like
                # `"skip-confirm-no"` that's not in the literal union.
                decision: str = decide_fill(
                    section=d.section,
                    sub_key=d.sub_key,
                    skip_reason=None,
                    live=args.live,
                    allowed_sections=allowed_sections - skip_sections_runtime,
                )

                if decision == "skip-account":
                    # Hand off to the credential hook (#341). The bank
                    # value is a documentation pointer to credentials.toml;
                    # honor relative paths from CWD and re-apply the
                    # runtime-roots guard before any I/O.
                    bank_path = Path(d.value)
                    if not bank_path.is_absolute():
                        bank_path = (Path.cwd() / bank_path).resolve()
                    assert_not_blocked_runtime_input(bank_path)
                    ats, tenant = infer_ats_tenant(page_url)
                    host = urlparse(page_url).hostname or ""
                    # If inference failed but we already prompted on
                    # this host, reuse the resolved pair instead of
                    # asking the user again for every password label.
                    if ats is None and tenant is None and host in host_ats_tenant_cache:
                        ats, tenant = host_ats_tenant_cache[host]
                    cred_result = handle_credential_match(
                        ats=ats,
                        tenant=tenant,
                        page_url=page_url,
                        prompter=prompter,
                        credentials_path=bank_path,
                    )
                    if host:
                        host_ats_tenant_cache[host] = (
                            cred_result.ats,
                            cred_result.tenant,
                        )
                    cred_key = (cred_result.ats, cred_result.tenant)
                    if cred_key not in credential_seen:
                        credential_seen.add(cred_key)
                        print(cred_result.message)
                    entry = {
                        "outcome": "match",
                        # `decision` populated so `_decision_summary`
                        # buckets these under `match[skip-account]`
                        # uniformly with other gated matches.
                        "decision": decision,
                        "label": lbl,
                        "type": ftype,
                        "section": d.section,
                        "sub_key": d.sub_key,
                        # Hard-redact regardless of --show-values:
                        # password belongs only on terminal + the
                        # credentials.toml file, never the capture JSON.
                        "value": f"<credential-store: {cred_result.ats}.{cred_result.tenant}>",
                        "matched_synonym": d.matched_synonym,
                    }
                    print(
                        f"  [would-fill]  {lbl[:55]:55s} → "
                        f"{d.section}.{d.sub_key:25s} = "
                        f"<credential-store: {cred_result.ats}.{cred_result.tenant}>"
                    )
                    decisions.append(entry)
                    new += 1
                    continue

                # Single source of truth for redaction so JSON + terminal
                # output can never disagree (e.g. drift from a future tweak
                # to only one of them and accidentally leak PII to one sink).
                display_value = d.value if args.show_values else _redact(d.value)

                if decision == "fill" and args.confirm_before_fill:
                    # Loop until the user gives one of the four
                    # documented answers. Treating typos / empty Enter
                    # as implicit "yes" would let a slip of the
                    # keyboard fill a sensitive field — defeating the
                    # whole point of --confirm-before-fill.
                    prompt = (
                        f"  fill {d.section}.{d.sub_key} = "
                        f"{display_value!r}? [y/n/s=skip-section/q=quit]: "
                    )
                    while True:
                        resp = input(prompt).strip().lower()
                        if resp == "y":
                            break
                        if resp == "n":
                            decision = "skip-confirm-no"
                            break
                        if resp == "s":
                            skip_sections_runtime.add(d.section)
                            decision = "skip-confirm-section"
                            break
                        if resp == "q":
                            # Flag the main loop to exit via the
                            # close-handling path; closing the context
                            # here triggers the wait_for_event("close")
                            # immediately so the user doesn't wait the
                            # full heartbeat interval.
                            quit_requested[0] = True
                            decision = "skip-quit"
                            try:
                                page_holder[0].context.close()
                            except Exception:
                                pass
                            break
                        prompt = "  please answer y / n / s / q: "

                if decision == "fill":
                    page = page_holder[0]
                    if page is None:
                        outcome_str, err = "fill-error", "page not ready"
                    else:
                        outcome_str, err = _perform_live_fill(page, fld, d)
                    entry = {
                        "outcome": outcome_str,
                        "label": lbl,
                        "type": ftype,
                        "section": d.section,
                        "sub_key": d.sub_key,
                        "value": display_value,
                        "matched_synonym": d.matched_synonym,
                    }
                    if err:
                        entry["error"] = err
                    # ASCII markers — matches the skip-path posture
                    # so encoding-restricted stdouts (Windows shells,
                    # some redirect targets) never UnicodeEncodeError.
                    marker = "OK" if outcome_str == "filled" else "!!"
                    err_suffix = f"  [{err}]" if err else ""
                    print(
                        f"  [{outcome_str:11s}] {marker} {lbl[:50]:50s} → "
                        f"{d.section}.{d.sub_key:25s} = {display_value!r}"
                        f"{err_suffix}"
                    )
                else:
                    # Log only — dry-run or gated. Includes the
                    # decision name so capture-readers can distinguish
                    # "didn't fill because --live off" from "didn't fill
                    # because section not whitelisted" without re-running.
                    entry = {
                        "outcome": "match",
                        "decision": decision,
                        "label": lbl,
                        "type": ftype,
                        "section": d.section,
                        "sub_key": d.sub_key,
                        "value": display_value,
                        "matched_synonym": d.matched_synonym,
                    }
                    # Legacy tag for backwards-compat: 'skip-dry-run'
                    # was previously logged as `[would-fill]`.
                    tag = "would-fill" if decision == "skip-dry-run" else decision
                    print(
                        f"  [{tag:18s}] {lbl[:50]:50s} → "
                        f"{d.section}.{d.sub_key:25s} = {display_value!r}"
                    )
            else:
                assert isinstance(d, Skip)
                entry = {
                    "outcome": "skip",
                    "reason": d.reason,
                    "label": lbl,
                    "type": ftype,
                    "detail": d.detail,
                }
                tag = "honeypot" if d.reason == "honeypot" else d.reason
                # ASCII-only marker so the driver doesn't crash on
                # encoding-restricted stdouts (some Windows shells,
                # certain redirect targets).
                marker = "!!" if d.reason == "honeypot" else "·"
                print(f"  [skip:{tag:11s}] {marker} {lbl[:55]}")
            decisions.append(entry)
            new += 1
        if new:
            write_decisions()

    fields_flushed = [False]

    with launch_stealth_chrome(user_data_dir=args.profile_dir) as context:

        def flush_chunk(label: str) -> bool:
            chunk_counter[0] += 1
            path = chunk_dir / f"chunk-{chunk_counter[0]:03d}-{label}.zip"
            try:
                context.tracing.stop_chunk(path=str(path))
                return True
            except Exception:
                return False

        def flush_final() -> None:
            if fields_flushed[0]:
                return
            fields_flushed[0] = True
            write_decisions()
            summary = _decision_summary(decisions)
            mode_str = "live" if args.live else "dry-run"
            print(f"\n[flush] {mode_str} complete.")
            print(f"  decisions: {decisions_path}  ({len(decisions)} fields)")
            for k in sorted(summary.keys()):
                print(f"    {k:30s} {summary[k]}")

        context.tracing.start(snapshots=True, screenshots=True, sources=False)
        context.tracing.start_chunk()
        context.add_init_script(EXTRACTOR_JS)
        context.on("close", lambda _ctx: flush_final())

        page = context.pages[0] if context.pages else context.new_page()
        # Make the page reachable from on_snapshot for the live-fill
        # path. on_snapshot is defined above the `with` block so it
        # can't reference `page` directly.
        page_holder[0] = page
        page.expose_function("__claudePush", on_snapshot)
        context.on(
            "page",
            lambda new_page: new_page.expose_function("__claudePush", on_snapshot),
        )

        try:
            page.goto(args.url)
            if args.live:
                print(
                    f"\n=== LIVE MODE — sections enabled: "
                    f"{','.join(sorted(allowed_sections)) or '(none)'} ==="
                )
                print(
                    f"    Typing delay range: {type_delay_range[0]}–"
                    f"{type_delay_range[1]} ms. Honeypots, passwords, "
                    "and work_experience never auto-fill."
                )
                if args.confirm_before_fill:
                    print("    Each fill will pause for confirmation.")
            else:
                print("\n=== DRY-RUN MODE — no fields will be filled. ===")
                print("    Drive the apply page manually; the matcher logs decisions")
            print("    in real time. Close the Chrome window when done.\n")
            while True:
                # Check the quit flag first — it's set when the user
                # answered "q" to a --confirm-before-fill prompt and
                # the on_snapshot handler already triggered
                # `context.close()`. Belt-and-braces: even if the close
                # event fired before we entered this branch, the flag
                # gives the loop a definitive exit signal.
                if quit_requested[0]:
                    break
                try:
                    context.wait_for_event("close", timeout=CHUNK_INTERVAL_S * 1000)
                    break
                except PlaywrightTimeoutError:
                    if quit_requested[0]:
                        break
                    if not flush_chunk("heartbeat"):
                        break
                    context.tracing.start_chunk()
                except KeyboardInterrupt:
                    print("\n[interrupted]")
                    flush_chunk("interrupt")
                    break
            flush_chunk("final")
            flush_final()
        except Exception as e:
            print(f"\n[error during session: {e}]")
            flush_chunk("exception")
            flush_final()
            raise
        finally:
            flush_final()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
