#!/usr/bin/env python3
"""Request a Copilot PR review kickoff comment using gh CLI.

This helper posts an issue comment that triggers Copilot review flow:
`@copilot review`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        required=True,
        help="Repository in owner/name format (for example: jsmithpkp21/resume-builder)",
    )
    parser.add_argument("--pr", required=True, type=int, help="Pull request number")
    parser.add_argument(
        "--sha",
        default="",
        help="Optional commit SHA to include in the kickoff message",
    )
    parser.add_argument(
        "--skip-duplicate-check",
        action="store_true",
        help="Always post, even if a matching kickoff comment already exists",
    )
    return parser.parse_args()


def _run_gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            check=check,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise RuntimeError(
            "GitHub CLI (gh) not found or not executable. Install from https://cli.github.com/ "
            "and ensure it is available on PATH."
        ) from exc


def _ensure_gh_auth() -> None:
    status = _run_gh("auth", "status", check=False)
    if status.returncode == 0:
        return

    message = [
        "ERROR: gh is not authenticated. Run: gh auth login",
        (
            "If GITHUB_TOKEN is exported, verify it is valid or unset it "
            "(stale tokens can override stored credentials and cause 401s)."
        ),
    ]
    stderr = status.stderr.strip()
    if stderr:
        message.append(stderr)
    raise RuntimeError("\n".join(message))


def _kickoff_body(sha: str) -> str:
    if sha:
        return f"@copilot review\n\nAuto-kickoff after push `{sha[:7]}`."
    return "@copilot review"


def _fetch_issue_comments(repo: str, pr: int) -> list[dict[str, object]]:
    """Fetch all issue comments using explicit per_page/page pagination.

    Avoids ``--paginate`` which can emit one JSON document per page,
    making ``json.loads`` of the combined stdout unreliable on large PRs.
    """
    page = 1
    per_page = 100
    merged: list[dict[str, object]] = []
    while True:
        endpoint = f"repos/{repo}/issues/{pr}/comments?per_page={per_page}&page={page}"
        response = _run_gh("api", endpoint)
        batch: list[dict[str, object]] = json.loads(response.stdout)
        if not batch:
            break
        merged.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return merged


def _existing_kickoff_matches(
    *, repo: str, pr: int, expected_body: str, short_sha: str
) -> bool:
    comments = _fetch_issue_comments(repo, pr)
    for comment in reversed(comments):
        body = str(comment.get("body") or "")
        normalized = body.strip()
        # Exact body match remains the strongest duplicate signal.
        if expected_body == body:
            return True
        # If SHA was provided, keep strict marker matching as before.
        if short_sha and normalized.endswith(f"Auto-kickoff after push `{short_sha}`."):
            return True
        # Even without --sha, treat prior kickoff bodies/markers as duplicates.
        if normalized.startswith("@copilot review"):
            return True
        if "Auto-kickoff after push `" in normalized:
            return True
    return False


def main() -> int:
    args = parse_args()
    try:
        _ensure_gh_auth()
        short_sha = args.sha[:7]
        body = _kickoff_body(args.sha)

        if not args.skip_duplicate_check and _existing_kickoff_matches(
            repo=args.repo,
            pr=args.pr,
            expected_body=body,
            short_sha=short_sha,
        ):
            print("copilot kickoff already present; skipped")
            return 0

        _run_gh(
            "api",
            "-X",
            "POST",
            f"repos/{args.repo}/issues/{args.pr}/comments",
            "-f",
            f"body={body}",
        )
        print(
            json.dumps(
                {
                    "repo": args.repo,
                    "pr": args.pr,
                    "sha": short_sha,
                    "posted_at_utc": datetime.now(UTC).isoformat(),
                },
                indent=2,
            )
        )
        return 0
    except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        message = str(exc).strip()
        if message:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
