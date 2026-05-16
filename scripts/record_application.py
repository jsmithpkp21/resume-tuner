#!/usr/bin/env python3
"""Playwright-driven capture for a single manual job application.

Launches Chrome with a stealth-wrapped persistent profile, starts tracing,
injects the DOM-walking field extractor on every page, and lets the user
drive the application manually. Writes a trace zip + field-snapshot JSON
on exit — including unexpected exits (window closed, Ctrl-C, exception).

Companion to `scripts/fill_application.py` (dry-run filler, issue #319).
Phase 3-A research migrated to main as `job_apply_kit` + this script.

Usage:

    scripts/record_application.py <apply-url> [--slug <slug>] \\
        [--profile-dir <path>] [--capture-dir <path>]

Defaults:
    --slug         session-<unix-ts> if omitted
    --profile-dir  data/applications/.browser-profile (gitignored)
    --capture-dir  data/applications/_capture        (gitignored)

Outputs (under <capture-dir>):
    fields-<slug>-<ts>.json   per-step field snapshots (atomic-write, so
                              SIGKILL never leaves a truncated file)
    trace-<slug>-<ts>/        directory of chunked Playwright traces
                              (each chunk a viewable .zip)

Both default paths are gitignored, so captures stay local. Run match-
validation later via `python -m job_apply_kit.match_replay`.

Safety:
  - `--slug` is validated against `[A-Za-z0-9_-]` to prevent path-escape
    via `..` or path separators.
  - `--profile-dir` / `--capture-dir` are checked against the repo's
    blocked-runtime-roots policy (sandbox/, data/samples/) before any
    filesystem mkdir or write.

Privacy (#351):
  - The injected field extractor (`job_apply_kit.field_extractor.js`)
    intentionally does NOT capture user-typed values from inputs,
    textareas, contenteditables, or comboboxes. Capture files contain
    only labels + structural metadata, never passwords / SSNs / OTPs.
  - Radio + select `options` are emitted with `value` + `label` (page
    content) but never the user's current `checked` / `selected` choice.
  - Captures recorded *before* the #351 fix may still contain raw
    values on disk under `--capture-dir`. Purge with `rm -rf
    <capture-dir>` (default: `data/applications/_capture`) if those
    captures predate this script's install.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    from job_apply_kit import EXTRACTOR_JS, atomic_write_json, sanitize_slug
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
CHUNK_INTERVAL_S = 20  # flush a trace chunk every N seconds of activity


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="apply URL to open")
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
        help=f"output dir for traces + fields JSON (default: {DEFAULT_CAPTURE_DIR})",
    )
    args = parser.parse_args(argv)

    ts = int(time.time())
    slug = sanitize_slug(args.slug) if args.slug else f"session-{ts}"

    # Block writes to sandbox/, data/samples/, etc. — same policy as
    # build_resume.run_pipeline and validate_experience_data.
    assert_not_blocked_runtime_input(args.profile_dir)
    assert_not_blocked_runtime_input(args.capture_dir)

    args.capture_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir = args.capture_dir / f"trace-{slug}-{ts}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    fields_path = args.capture_dir / f"fields-{slug}-{ts}.json"
    chunk_counter = [0]

    snapshots: list[dict[str, Any]] = []

    def write_fields() -> None:
        # Atomic write: temp file + os.replace() so SIGKILL mid-write can't
        # leave fields_path truncated. Readers always see either the prior
        # full snapshot or the new full snapshot, never a partial.
        try:
            atomic_write_json(fields_path, snapshots)
        except OSError as e:
            print(f"  [warn] fields write failed: {e}")

    def on_snapshot(payload: dict[str, Any]) -> None:
        snapshots.append(payload)
        print(
            f"  [capture] step {len(snapshots)}: "
            f"{payload.get('url', '')[:80]}  "
            f"({len(payload.get('fields', []))} fields)"
        )
        write_fields()

    fields_flushed = [False]

    with launch_stealth_chrome(user_data_dir=args.profile_dir) as context:

        def flush_chunk(label: str) -> bool:
            """Write one trace chunk to disk. Returns True on success.

            Each chunk is a complete, viewable trace zip of activity since
            the previous start_chunk(). If the browser is already dead the
            chunk write fails — we ignore that and rely on prior chunks.
            """
            chunk_counter[0] += 1
            path = chunk_dir / f"chunk-{chunk_counter[0]:03d}-{label}.zip"
            try:
                context.tracing.stop_chunk(path=str(path))
                return True
            except Exception:
                # Playwright tracing has no narrow exception base; any
                # failure (browser already closed, disk I/O, tracing state)
                # just means this chunk is lost — prior chunks are on disk.
                return False

        def flush_fields_final() -> None:
            if fields_flushed[0]:
                return
            fields_flushed[0] = True
            write_fields()
            print(
                f"\n[flush] fields: {fields_path}  ({len(snapshots)} snapshots, "
                f"{chunk_counter[0]} trace chunks in {chunk_dir.name}/)"
            )

        context.tracing.start(snapshots=True, screenshots=True, sources=False)
        context.tracing.start_chunk()
        context.add_init_script(EXTRACTOR_JS)
        # Best-effort flush on context close — sync-API caveat: fires only
        # on the next Playwright call. The polling loop below is the actual
        # source of incremental durability.
        context.on("close", lambda _ctx: flush_fields_final())

        page = context.pages[0] if context.pages else context.new_page()
        page.expose_function("__claudePush", on_snapshot)
        context.on(
            "page",
            lambda new_page: new_page.expose_function("__claudePush", on_snapshot),
        )

        try:
            page.goto(args.url)
            print("\n=== Browser open. Drive the application manually. ===")
            print("    Resume upload, manual entry, captchas — all in the window.")
            print(f"    Trace chunks flush every {CHUNK_INTERVAL_S}s; field")
            print("    snapshots flush on every page-stable change. Close the")
            print("    Chrome window when done — driver exits. Ctrl-C aborts.\n")

            # Poll-with-timeout loop. wait_for_event raises Timeout when no
            # close happens within CHUNK_INTERVAL_S; use that as a heartbeat
            # to roll trace chunks and resume waiting.
            while True:
                try:
                    context.wait_for_event("close", timeout=CHUNK_INTERVAL_S * 1000)
                    break  # close fired
                except PlaywrightTimeoutError:
                    if not flush_chunk("heartbeat"):
                        break  # browser died mid-chunk; prior chunks are on disk
                    context.tracing.start_chunk()
                except KeyboardInterrupt:
                    print("\n[interrupted]")
                    flush_chunk("interrupt")
                    break

            # Best-effort final chunk (likely fails after a graceful close).
            flush_chunk("final")
            flush_fields_final()
        except Exception as e:  # noqa: BLE001
            # Recording-session boundary: any failure (Playwright, KeyboardInterrupt
            # was already handled above, downstream callbacks) must still
            # persist the trace + fields before propagating.
            print(f"\n[error during session: {e}]")
            flush_chunk("exception")
            flush_fields_final()
            raise
        finally:
            flush_fields_final()

    # The first chunk's label depends on how the session ended (heartbeat /
    # final / interrupt / exception), so print a glob pattern instead of
    # guessing a specific filename.
    print("\nOpen any chunk with:")
    print(f"  npx playwright show-trace {chunk_dir}/chunk-001-*.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
