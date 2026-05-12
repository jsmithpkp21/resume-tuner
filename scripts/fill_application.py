#!/usr/bin/env python3
"""Playwright-driven semi-auto filler — dry-run mode (issue #319 Phase 3-A).

Opens Chrome via the same stealth-wrapped persistent context as
`scripts/record_application.py`, injects the field extractor, and on each
stable snapshot runs `job_apply_kit.label_matcher.match` per field. In
dry-run mode it LOGS what it would fill but never calls page.fill() /
page.click().

Use the output to:
  1. Confirm the matcher does the right thing on a live apply page
  2. Spot synonyms missing from the answer bank
  3. Catch honeypot patterns the matcher hasn't seen yet

Live-fill execution + per-role Workday loop handling are future
sub-issues (Phase 3 deliverables B/C).

Usage:

    scripts/fill_application.py <apply-url> \\
        --bank data/applications/_answer_bank.toml \\
        [--slug <slug>] [--profile-dir <path>] [--capture-dir <path>] \\
        [--show-values]

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

Safety:
  - `--slug` is validated against `[A-Za-z0-9_-]` to prevent path-escape.
  - `--bank`, `--profile-dir`, `--capture-dir` are checked against the
    repo's blocked-runtime-roots policy before any filesystem I/O.
"""

from __future__ import annotations

import argparse
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from job_apply_kit import (
        EXTRACTOR_JS,
        Match,
        Skip,
        atomic_write_json,
        match,
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


def _redact(value: str) -> str:
    """Display-safe value fingerprint: never leaks contents, but still
    distinguishes different values via their length."""
    return f"<value len={len(value)}>"


def _decision_summary(decisions: list[dict[str, Any]]) -> dict[str, int]:
    """Summary counts by outcome — match / skip[honeypot] / skip[no-match] / skip[empty-value]."""
    out: dict[str, int] = {}
    for d in decisions:
        k = d["outcome"]
        if "reason" in d:
            k = f"skip[{d['reason']}]"
        out[k] = out.get(k, 0) + 1
    return out


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
    args = parser.parse_args(argv)

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

    # Per-field decisions accumulate here. Deduped by (label, type) so we
    # don't double-count fields that re-emit on every MutationObserver tick.
    decisions: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    def write_decisions() -> None:
        try:
            atomic_write_json(decisions_path, decisions)
        except OSError as e:
            print(f"  [warn] decisions write failed: {e}")

    def on_snapshot(payload: dict[str, Any]) -> None:
        fields = payload.get("fields", [])
        new = 0
        for fld in fields:
            lbl = (fld.get("label") or "").strip()
            ftype = fld.get("type", "")
            if not lbl:
                continue
            key = (lbl, ftype)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            d = match(lbl, bank)
            if isinstance(d, Match):
                # Single source of truth for redaction so JSON + terminal
                # output can never disagree (e.g. drift from a future tweak
                # to only one of them and accidentally leak PII to one sink).
                display_value = d.value if args.show_values else _redact(d.value)
                entry = {
                    "outcome": "match",
                    "label": lbl,
                    "type": ftype,
                    "section": d.section,
                    "sub_key": d.sub_key,
                    "value": display_value,
                    "matched_synonym": d.matched_synonym,
                }
                print(
                    f"  [would-fill]  {lbl[:55]:55s} → "
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
            print("\n[flush] dry-run complete.")
            print(f"  decisions: {decisions_path}  ({len(decisions)} fields)")
            for k in sorted(summary.keys()):
                print(f"    {k:25s} {summary[k]}")

        context.tracing.start(snapshots=True, screenshots=True, sources=False)
        context.tracing.start_chunk()
        context.add_init_script(EXTRACTOR_JS)
        context.on("close", lambda _ctx: flush_final())

        page = context.pages[0] if context.pages else context.new_page()
        page.expose_function("__claudePush", on_snapshot)
        context.on(
            "page",
            lambda new_page: new_page.expose_function("__claudePush", on_snapshot),
        )

        try:
            page.goto(args.url)
            print("\n=== DRY-RUN MODE — no fields will be filled. ===")
            print("    Drive the apply page manually; the matcher logs decisions")
            print("    in real time. Close the Chrome window when done.\n")
            while True:
                try:
                    context.wait_for_event("close", timeout=CHUNK_INTERVAL_S * 1000)
                    break
                except PlaywrightTimeoutError:
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
