#!/usr/bin/env python3
"""Summarize PR review threads and current owner response status.

This helper is intentionally lightweight for consumer-repo review passes.
It fetches PR review comments, groups them into root threads, and reports
whether each thread is unaddressed or already has an owner reply such as
"fixing:", "fixed in <sha>", "defer:", or "will not fix:".
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

ISO8601_Z_SUFFIX = "+00:00"


@dataclass(frozen=True)
class ReviewThreadSummary:
    root_id: int
    path: str
    line: int | None
    created_at: str
    author_login: str
    status: str
    root_body: str
    latest_owner_reply_id: int | None
    latest_owner_reply_body: str


@dataclass(frozen=True)
class ActionPlanItem:
    root_id: int
    current_status: str
    planned_action: str
    should_reply_now: bool
    rationale: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="GitHub repo in owner/name form, e.g. jsmithpkp21/resume-builder",
    )
    parser.add_argument(
        "--created-after",
        type=str,
        default="",
        help="Only include root comments created after this ISO-8601 timestamp",
    )
    parser.add_argument(
        "--owner-login",
        type=str,
        default="",
        help="Override GitHub login used to detect owner replies",
    )
    parser.add_argument(
        "--unaddressed-only",
        action="store_true",
        help="Only print root comments without an owner reply",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text",
    )
    parser.add_argument(
        "--root-ids",
        type=str,
        default="",
        help="Comma-separated root comment ids to include (for targeted review passes)",
    )
    parser.add_argument(
        "--action-plan-json",
        action="store_true",
        help="Emit action-plan JSON (fix/defer/wontfix suggestions with idempotent guard)",
    )
    parser.add_argument(
        "--default-action",
        choices=("fix", "defer", "wontfix"),
        default="fix",
        help="Default planned action for unaddressed comments when --action-plan-json is used",
    )
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Print phase timings to stderr",
    )
    parser.add_argument(
        "--expand-review-comments",
        action="store_true",
        help=("Explicitly enable per-review comment expansion (default behavior)."),
    )
    parser.add_argument(
        "--skip-review-expansion",
        action="store_false",
        dest="expand_review_comments",
        help=(
            "Skip per-review comment expansion to avoid N+1 API calls on large PRs "
            "(may miss review comments only visible via review-specific endpoints)."
        ),
    )
    parser.set_defaults(expand_review_comments=True)
    return parser.parse_args()


def _run_gh_json(*args: str) -> Any:
    try:
        result = subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) not found or could not be executed. Install it from https://cli.github.com/."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        message = [
            f"GitHub API command failed (exit {exc.returncode}): {' '.join(exc.cmd)}",
        ]
        if stderr:
            message.append(f"stderr: {stderr}")
        if stdout:
            message.append(f"stdout: {stdout}")
        raise RuntimeError("\n".join(message)) from exc
    return json.loads(result.stdout)


def _run_gh_json_paginated(*args: str) -> list[dict[str, Any]]:
    """Fetch paginated GitHub API list responses reliably.

    Avoids silent truncation on large PRs where default page sizes hide comments.
    """
    page = 1
    per_page = 100
    merged: list[dict[str, Any]] = []
    while True:
        endpoint = args[-1]
        if "?" in endpoint:
            paged_endpoint = f"{endpoint}&per_page={per_page}&page={page}"
        else:
            paged_endpoint = f"{endpoint}?per_page={per_page}&page={page}"
        payload = _run_gh_json(*args[:-1], paged_endpoint)
        if not isinstance(payload, list):
            raise ValueError("Expected paginated API response to be a list")
        if not payload:
            break
        merged.extend(payload)
        if len(payload) < per_page:
            break
        page += 1
    return merged


def _ensure_gh_auth() -> None:
    try:
        subprocess.run(
            ["gh", "auth", "status"],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) not found or could not be executed. Install it from https://cli.github.com/."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        message = [
            "GitHub CLI authentication failed. Run: gh auth login",
            "If GITHUB_TOKEN is exported, verify or unset it (stale tokens can override stored credentials and cause 401s).",
        ]
        if stderr:
            message.append(f"gh auth status output: {stderr}")
        raise RuntimeError("\n".join(message)) from exc


def _current_login() -> str:
    payload = _run_gh_json("api", "user")
    return str(payload["login"])


def _fetch_all_review_comments(
    repo: str, pr: int, *, expand_review_comments: bool = True
) -> list[dict[str, Any]]:
    comments = _run_gh_json_paginated("api", f"repos/{repo}/pulls/{pr}/comments")
    merged_by_id: dict[int, dict[str, Any]] = {
        int(comment["id"]): comment for comment in comments
    }

    if expand_review_comments:
        reviews = _run_gh_json_paginated("api", f"repos/{repo}/pulls/{pr}/reviews")
        for review in reviews:
            review_id = int(review["id"])
            for comment in _run_gh_json_paginated(
                "api", f"repos/{repo}/pulls/{pr}/reviews/{review_id}/comments"
            ):
                merged_by_id[int(comment["id"])] = comment

    return sorted(
        merged_by_id.values(), key=lambda item: (item["created_at"], item["id"])
    )


def _parse_iso8601(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", ISO8601_Z_SUFFIX))
    if parsed.tzinfo is None:
        raise ValueError(
            "--created-after must include timezone info (for example: 2026-04-20T16:18:00Z)"
        )
    return parsed


def _parse_root_ids(raw: str) -> set[int]:
    if not raw.strip():
        return set()
    parsed: set[int] = set()
    for token in raw.split(","):
        cleaned = token.strip()
        if not cleaned:
            continue
        try:
            parsed.add(int(cleaned))
        except ValueError as exc:
            raise ValueError(f"Invalid root id: {cleaned}") from exc
    return parsed


def _reply_status(body: str) -> str:
    lowered = body.strip().lower()
    if lowered.startswith("fixing:"):
        return "fixing"
    if lowered.startswith("fixed in "):
        return "fixed"
    if lowered.startswith("defer:"):
        return "defer"
    if lowered.startswith("will not fix:"):
        return "will_not_fix"
    return "replied"


def summarize_review_threads(
    comments: list[dict[str, Any]],
    *,
    owner_login: str,
    created_after: str = "",
    unaddressed_only: bool = False,
    root_ids: set[int] | None = None,
) -> list[ReviewThreadSummary]:
    roots = [comment for comment in comments if comment.get("in_reply_to_id") is None]
    replies_by_root: dict[int, list[dict[str, Any]]] = {}
    for comment in comments:
        reply_to = comment.get("in_reply_to_id")
        if reply_to is None:
            continue
        replies_by_root.setdefault(int(reply_to), []).append(comment)

    created_after_dt = _parse_iso8601(created_after) if created_after else None
    summaries: list[ReviewThreadSummary] = []
    for root in roots:
        root_id = int(root["id"])
        if root_ids and root_id not in root_ids:
            continue
        root_created_at = str(root["created_at"])
        if (
            created_after_dt is not None
            and _parse_iso8601(root_created_at) <= created_after_dt
        ):
            continue

        owner_replies = [
            reply
            for reply in replies_by_root.get(int(root["id"]), [])
            if str(reply["user"]["login"]) == owner_login
        ]
        latest_owner_reply = None
        if owner_replies:
            latest_owner_reply = max(owner_replies, key=lambda item: item["created_at"])
            status = _reply_status(str(latest_owner_reply.get("body", "")))
        else:
            status = "unaddressed"

        if unaddressed_only and status != "unaddressed":
            continue

        summaries.append(
            ReviewThreadSummary(
                root_id=root_id,
                path=str(root.get("path") or ""),
                line=root.get("line"),
                created_at=root_created_at,
                author_login=str(root["user"]["login"]),
                status=status,
                root_body=str(root.get("body") or ""),
                latest_owner_reply_id=(
                    int(latest_owner_reply["id"])
                    if latest_owner_reply is not None
                    else None
                ),
                latest_owner_reply_body=(
                    str(latest_owner_reply.get("body") or "")
                    if latest_owner_reply is not None
                    else ""
                ),
            )
        )

    return sorted(summaries, key=lambda item: (item.created_at, item.root_id))


def build_action_plan(
    summaries: list[ReviewThreadSummary], *, default_action: str
) -> list[ActionPlanItem]:
    plan: list[ActionPlanItem] = []
    for summary in summaries:
        if summary.status == "fixed":
            plan.append(
                ActionPlanItem(
                    root_id=summary.root_id,
                    current_status=summary.status,
                    planned_action="skip",
                    should_reply_now=False,
                    rationale="Already has a fixed-in reply.",
                )
            )
            continue
        if summary.status in {"fixing", "defer", "will_not_fix"}:
            plan.append(
                ActionPlanItem(
                    root_id=summary.root_id,
                    current_status=summary.status,
                    planned_action="skip",
                    should_reply_now=False,
                    rationale="Idempotent guard: matching owner status already present.",
                )
            )
            continue

        mapped = {
            "fix": "fixing",
            "defer": "defer",
            "wontfix": "will_not_fix",
        }[default_action]
        plan.append(
            ActionPlanItem(
                root_id=summary.root_id,
                current_status=summary.status,
                planned_action=mapped,
                should_reply_now=True,
                rationale="Unaddressed thread; reply required before code edits.",
            )
        )
    return plan


def _print_text(summaries: list[ReviewThreadSummary]) -> None:
    if not summaries:
        print("No matching review threads.")
        return
    for summary in summaries:
        print(
            f"[{summary.status}] id={summary.root_id} path={summary.path} "
            f"line={summary.line} created_at={summary.created_at}"
        )
        print(summary.root_body.replace("\n", " "))
        if summary.latest_owner_reply_body:
            print(
                f"owner_reply: {summary.latest_owner_reply_body.replace(chr(10), ' ')}"
            )
        print("---")


def _print_timing(enabled: bool, phase: str, started_at: float) -> None:
    if not enabled:
        return
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    print(f"timing: {phase}={elapsed_ms:.1f}ms", file=sys.stderr)


def main() -> int:
    args = parse_args()
    try:
        total_start = time.perf_counter()
        phase_start = time.perf_counter()
        _ensure_gh_auth()
        _print_timing(args.timing, "auth", phase_start)

        phase_start = time.perf_counter()
        owner_login = args.owner_login or _current_login()
        comments = _fetch_all_review_comments(
            args.repo,
            args.pr,
            expand_review_comments=args.expand_review_comments,
        )
        _print_timing(args.timing, "fetch", phase_start)

        phase_start = time.perf_counter()
        root_ids = _parse_root_ids(args.root_ids)
        summaries = summarize_review_threads(
            comments,
            owner_login=owner_login,
            created_after=args.created_after,
            unaddressed_only=args.unaddressed_only,
            root_ids=root_ids,
        )
        _print_timing(args.timing, "summarize", phase_start)

        if args.action_plan_json:
            phase_start = time.perf_counter()
            plan = build_action_plan(summaries, default_action=args.default_action)
            print(json.dumps([item.__dict__ for item in plan], indent=2))
            _print_timing(args.timing, "plan", phase_start)
        elif args.json:
            print(json.dumps([summary.__dict__ for summary in summaries], indent=2))
        else:
            _print_text(summaries)
        _print_timing(args.timing, "total", total_start)
        return 0
    except (subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        message = str(exc).strip()
        if message:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
