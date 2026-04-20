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
    return parser.parse_args()


def _run_gh_json(*args: str) -> Any:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _ensure_gh_auth() -> None:
    subprocess.run(["gh", "auth", "status"], check=True, capture_output=True, text=True)


def _current_login() -> str:
    payload = _run_gh_json("api", "user")
    return str(payload["login"])


def _fetch_all_review_comments(repo: str, pr: int) -> list[dict[str, Any]]:
    comments = _run_gh_json("api", f"repos/{repo}/pulls/{pr}/comments")
    reviews = _run_gh_json("api", f"repos/{repo}/pulls/{pr}/reviews")

    merged_by_id: dict[int, dict[str, Any]] = {
        int(comment["id"]): comment for comment in comments
    }
    for review in reviews:
        review_id = int(review["id"])
        for comment in _run_gh_json(
            "api", f"repos/{repo}/pulls/{pr}/reviews/{review_id}/comments"
        ):
            merged_by_id[int(comment["id"])] = comment

    return sorted(
        merged_by_id.values(), key=lambda item: (item["created_at"], item["id"])
    )


def _parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", ISO8601_Z_SUFFIX))


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
                root_id=int(root["id"]),
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


def main() -> int:
    args = parse_args()
    try:
        _ensure_gh_auth()
        owner_login = args.owner_login or _current_login()
        comments = _fetch_all_review_comments(args.repo, args.pr)
        summaries = summarize_review_threads(
            comments,
            owner_login=owner_login,
            created_after=args.created_after,
            unaddressed_only=args.unaddressed_only,
        )
        if args.json:
            print(json.dumps([summary.__dict__ for summary in summaries], indent=2))
        else:
            _print_text(summaries)
        return 0
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
