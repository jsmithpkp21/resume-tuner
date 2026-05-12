"""Offline matcher validation against captured field snapshots.

Walks one or more `fields-<slug>-<ts>.json` files (the output format that
`scripts/record_application.py` writes to its capture dir), runs
`label_matcher.match` on every distinct label seen per session, and reports
per-session + overall match-rate stats:

  - match                    — answer-bank entry resolved to a non-empty value
  - skip[honeypot]           — label matched a known anti-bot honeypot pattern
  - skip[empty-value]        — synonym matched but the bank's value is blank/TODO
  - skip[unresolved-sub-key] — synonym matched but the matcher couldn't pick a
                               sub-key (resolver heuristic miss, or multi-field
                               section with no resolver registered)
  - skip[no-match]           — no synonym matched (structural/custom/page-chrome)

Used to validate the matcher against real captures before doing anything
live. The CLI also serves as the canonical "how confident is my answer
bank" health check: rising `no-match` rate suggests synonyms missing;
rising `empty-value` rate suggests TODOs in the bank that should be filled;
rising `unresolved-sub-key` rate suggests the matcher's per-section
resolvers in `label_matcher._SUB_KEY_RESOLVERS` need new heuristic branches
or that a multi-field section needs its first resolver.

Example:

    python -m job_apply_kit.match_replay \\
        --bank data/applications/_answer_bank.toml \\
        data/applications/_capture/fields-*.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path
from typing import TextIO

from resume_builder._runtime_guard import assert_not_blocked_runtime_input

from .label_matcher import Match, Skip, match


def replay(
    *,
    answer_bank: dict[str, object],
    capture_paths: list[Path],
    verbose: bool = False,
    out: TextIO | None = None,
) -> int:
    """Replay the matcher against captured fields-*.json files.

    Returns the total number of distinct labels matched across all captures
    (callers that want stricter pass/fail can wrap this).

    Output (per-session + overall summary) is written to `out` (default
    `sys.stdout`). With `verbose=True`, each per-label decision is logged.
    """
    sink = out if out is not None else sys.stdout
    total_matches = 0
    total_skips: Counter[str] = Counter()
    total_distinct_labels = 0

    for fp in capture_paths:
        # Derive a human-readable slug from the filename for the per-session header
        slug = fp.stem.removeprefix("fields-")
        # Strip trailing -<ts> (digits) so "01-becu-staff-sdet-1778440157" becomes "01-becu-staff-sdet"
        ts_split = slug.rsplit("-", 1)
        if len(ts_split) == 2 and ts_split[1].isdigit():
            slug = ts_split[0]
        # UTF-8 explicit + tolerant of partial captures: the recorder writes
        # incrementally and can be SIGKILLed mid-write (atomic-write helper
        # exists but older captures may pre-date it). Emit a warning and
        # continue rather than crashing the whole replay on one bad file.
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"\n=== {slug} === (skipped: {fp.name} is not valid JSON: {exc})",
                file=sink,
            )
            continue
        except OSError as exc:
            print(f"\n=== {slug} === (skipped: {exc})", file=sink)
            continue

        labels_seen: set[str] = set()
        for snap in data:
            for fld in snap.get("fields", []):
                lbl = (fld.get("label") or "").strip()
                if lbl:
                    labels_seen.add(lbl)

        per_session_match = 0
        per_session_skip: Counter[str] = Counter()

        print(f"\n=== {slug} ({len(labels_seen)} distinct labels) ===", file=sink)
        for lbl in sorted(labels_seen, key=str.lower):
            d = match(lbl, answer_bank)
            if isinstance(d, Match):
                per_session_match += 1
                if verbose:
                    print(
                        f"  ✓  Match {d.section}.{d.sub_key:20s} ← {lbl[:60]}"
                        f"    (syn: {d.matched_synonym[:40]})",
                        file=sink,
                    )
            else:
                assert isinstance(d, Skip)
                per_session_skip[d.reason] += 1
                if verbose:
                    print(f"  ·  Skip[{d.reason:11s}] {lbl[:60]}", file=sink)

        denom = len(labels_seen) or 1
        print(
            f"  matched     : {per_session_match} / {denom}  "
            f"({per_session_match / denom * 100:.1f}%)",
            file=sink,
        )
        for reason, n in per_session_skip.most_common():
            print(f"  skip[{reason:11s}]: {n}", file=sink)

        total_matches += per_session_match
        for r, n in per_session_skip.items():
            total_skips[r] += n
        total_distinct_labels += len(labels_seen)

    print("\n" + "=" * 60, file=sink)
    print("OVERALL", file=sink)
    print("=" * 60, file=sink)
    denom = total_distinct_labels or 1
    print(
        f"distinct labels across {len(capture_paths)} captures: {total_distinct_labels}",
        file=sink,
    )
    print(
        f"matched     : {total_matches} ({total_matches / denom * 100:.1f}%)",
        file=sink,
    )
    for reason, n in total_skips.most_common():
        print(f"skip[{reason:11s}]: {n} ({n / denom * 100:.1f}%)", file=sink)
    return total_matches


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="fields-*.json files to replay",
    )
    p.add_argument(
        "--bank",
        type=Path,
        required=True,
        help="Path to the answer bank TOML (typically data/applications/_answer_bank.toml).",
    )
    p.add_argument(
        "--verbose", action="store_true", help="print every per-label decision"
    )
    args = p.parse_args(argv)

    # Honor the repo's blocked-runtime-roots policy: this CLI reads
    # user-supplied paths and must reject any that resolve under a blocked
    # root (consistent with build_resume.py, scripts/record_application.py,
    # scripts/fill_application.py).
    assert_not_blocked_runtime_input(args.bank)
    for fp in args.files:
        assert_not_blocked_runtime_input(fp)

    # Deterministic TOML parse: read as bytes so tomllib doesn't depend on
    # the OS's default text decoding.
    with args.bank.open("rb") as f:
        bank = tomllib.load(f)
    replay(answer_bank=bank, capture_paths=args.files, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
