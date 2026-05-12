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
        [--slug <slug>] [--profile-dir <path>] [--capture-dir <path>]

Outputs (under <capture-dir>):
    fill-decisions-<slug>-<ts>.json  per-field decision log
    trace-<slug>-<ts>/               chunked Playwright traces
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from job_apply_kit import EXTRACTOR_JS, Match, Skip, match
    from playwright_stealth_kit import launch_stealth_chrome
except ImportError:
    sys.stderr.write(
        "playwright + playwright-stealth required. Install with:\n"
        "  pip install playwright playwright-stealth\n"
    )
    sys.exit(2)


DEFAULT_PROFILE_DIR = Path("data/applications/.browser-profile")
DEFAULT_CAPTURE_DIR = Path("data/applications/_capture")
CHUNK_INTERVAL_S = 20


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
        help="output filename slug (default: session-<ts>)",
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
    args = parser.parse_args(argv)

    ts = int(time.time())
    slug = args.slug or f"session-{ts}"
    args.capture_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = args.capture_dir / f"trace-{slug}-{ts}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = args.capture_dir / f"fill-decisions-{slug}-{ts}.json"
    chunk_counter = [0]

    bank = tomllib.loads(args.bank.read_text())
    print(
        f"[setup] answer bank loaded: {len(bank)} sections, "
        f"{sum(len(v.get('synonyms', [])) for v in bank.values() if isinstance(v, dict))} synonyms"
    )

    # Per-field decisions accumulate here. Deduped by (label, type) so we
    # don't double-count fields that re-emit on every MutationObserver tick.
    decisions: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    def write_decisions() -> None:
        try:
            decisions_path.write_text(json.dumps(decisions, indent=2))
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
                entry = {
                    "outcome": "match",
                    "label": lbl,
                    "type": ftype,
                    "section": d.section,
                    "sub_key": d.sub_key,
                    "value": d.value,
                    "matched_synonym": d.matched_synonym,
                }
                print(
                    f"  [would-fill]  {lbl[:55]:55s} → "
                    f"{d.section}.{d.sub_key:25s} = {d.value!r}"
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
                marker = "🛑" if d.reason == "honeypot" else "·"
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
