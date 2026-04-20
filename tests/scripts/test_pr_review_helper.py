from __future__ import annotations

import subprocess

import pytest

from scripts.pr_review_helper import (
    _fetch_all_review_comments,
    _parse_iso8601,
    _run_gh_json,
    build_action_plan,
    summarize_review_threads,
)


def _comment(
    *,
    comment_id: int,
    body: str,
    created_at: str,
    user: str = "Copilot",
    in_reply_to_id: int | None = None,
    path: str = "scripts/build_resume.py",
    line: int | None = 10,
) -> dict[str, object]:
    return {
        "id": comment_id,
        "body": body,
        "created_at": created_at,
        "user": {"login": user},
        "in_reply_to_id": in_reply_to_id,
        "path": path,
        "line": line,
    }


def test_summarize_review_threads_classifies_owner_reply_statuses() -> None:
    comments = [
        _comment(comment_id=1, body="root 1", created_at="2026-04-20T10:00:00Z"),
        _comment(
            comment_id=2,
            body="fixing: will patch this",
            created_at="2026-04-20T10:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=1,
        ),
        _comment(comment_id=3, body="root 2", created_at="2026-04-20T11:00:00Z"),
        _comment(
            comment_id=4,
            body="fixed in abc123",
            created_at="2026-04-20T11:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=3,
        ),
        _comment(comment_id=5, body="root 3", created_at="2026-04-20T12:00:00Z"),
        _comment(
            comment_id=6,
            body="defer: tracked in #125",
            created_at="2026-04-20T12:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=5,
        ),
        _comment(comment_id=7, body="root 4", created_at="2026-04-20T13:00:00Z"),
        _comment(
            comment_id=8,
            body="will not fix: intentional in this repo",
            created_at="2026-04-20T13:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=7,
        ),
        _comment(comment_id=9, body="root 5", created_at="2026-04-20T14:00:00Z"),
    ]

    summaries = summarize_review_threads(comments, owner_login="jsmithpkp21")

    assert [summary.status for summary in summaries] == [
        "fixing",
        "fixed",
        "defer",
        "will_not_fix",
        "unaddressed",
    ]


def test_summarize_review_threads_filters_created_after_and_unaddressed() -> None:
    comments = [
        _comment(comment_id=1, body="old root", created_at="2026-04-20T10:00:00Z"),
        _comment(comment_id=2, body="new root 1", created_at="2026-04-20T16:18:24Z"),
        _comment(
            comment_id=3,
            body="fixing: handling new root 1",
            created_at="2026-04-20T16:19:00Z",
            user="jsmithpkp21",
            in_reply_to_id=2,
        ),
        _comment(comment_id=4, body="new root 2", created_at="2026-04-20T16:18:25Z"),
    ]

    filtered = summarize_review_threads(
        comments,
        owner_login="jsmithpkp21",
        created_after="2026-04-20T16:18:00Z",
    )
    assert [summary.root_id for summary in filtered] == [2, 4]

    unaddressed = summarize_review_threads(
        comments,
        owner_login="jsmithpkp21",
        created_after="2026-04-20T16:18:00Z",
        unaddressed_only=True,
    )
    assert [summary.root_id for summary in unaddressed] == [4]
    assert unaddressed[0].status == "unaddressed"


def test_summarize_review_threads_handles_reply_added_from_separate_comment_source() -> (
    None
):
    root_comments = [
        _comment(comment_id=10, body="new root", created_at="2026-04-20T16:18:25Z"),
    ]
    review_comments = [
        _comment(
            comment_id=11,
            body="fixing: handling via review-specific comments endpoint",
            created_at="2026-04-20T16:47:06Z",
            user="jsmithpkp21",
            in_reply_to_id=10,
        )
    ]

    summaries = summarize_review_threads(
        root_comments + review_comments,
        owner_login="jsmithpkp21",
        created_after="2026-04-20T16:18:00Z",
    )

    assert len(summaries) == 1
    assert summaries[0].root_id == 10
    assert summaries[0].status == "fixing"


def test_summarize_review_threads_filters_specific_root_ids() -> None:
    comments = [
        _comment(comment_id=21, body="root a", created_at="2026-04-20T10:00:00Z"),
        _comment(comment_id=22, body="root b", created_at="2026-04-20T11:00:00Z"),
        _comment(
            comment_id=23,
            body="fixing: root b",
            created_at="2026-04-20T11:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=22,
        ),
    ]

    summaries = summarize_review_threads(
        comments,
        owner_login="jsmithpkp21",
        root_ids={22},
    )

    assert len(summaries) == 1
    assert summaries[0].root_id == 22
    assert summaries[0].status == "fixing"


def test_build_action_plan_skips_threads_with_existing_owner_status() -> None:
    comments = [
        _comment(
            comment_id=31, body="root unaddressed", created_at="2026-04-20T10:00:00Z"
        ),
        _comment(comment_id=32, body="root fixing", created_at="2026-04-20T11:00:00Z"),
        _comment(
            comment_id=33,
            body="fixing: already acknowledged",
            created_at="2026-04-20T11:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=32,
        ),
        _comment(comment_id=34, body="root fixed", created_at="2026-04-20T12:00:00Z"),
        _comment(
            comment_id=35,
            body="fixed in abc123",
            created_at="2026-04-20T12:01:00Z",
            user="jsmithpkp21",
            in_reply_to_id=34,
        ),
    ]
    summaries = summarize_review_threads(comments, owner_login="jsmithpkp21")
    plan = build_action_plan(summaries, default_action="fix")
    by_id = {item.root_id: item for item in plan}

    assert by_id[31].planned_action == "fixing"
    assert by_id[31].should_reply_now is True
    assert by_id[32].planned_action == "skip"
    assert by_id[32].should_reply_now is False
    assert by_id[34].planned_action == "skip"
    assert by_id[34].should_reply_now is False


def test_parse_iso8601_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        _parse_iso8601("2026-04-20T16:18:00")


def test_run_gh_json_reports_missing_gh_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_oserror(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", _raise_oserror)

    with pytest.raises(RuntimeError, match=r"GitHub CLI \(gh\) not found"):
        _run_gh_json("api", "user")


def test_fetch_all_review_comments_can_skip_review_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_paginated(*args: str) -> list[dict[str, object]]:
        endpoint = args[-1]
        calls.append(endpoint)
        if endpoint.endswith("/pulls/123/comments"):
            return [
                _comment(comment_id=101, body="root", created_at="2026-04-20T10:00:00Z")
            ]
        return []

    monkeypatch.setattr(
        "scripts.pr_review_helper._run_gh_json_paginated", fake_paginated
    )

    comments = _fetch_all_review_comments(
        "owner/repo",
        123,
        expand_review_comments=False,
    )

    assert len(comments) == 1
    assert calls == ["repos/owner/repo/pulls/123/comments"]


def test_fetch_all_review_comments_expands_review_comment_endpoints_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_paginated(*args: str) -> list[dict[str, object]]:
        endpoint = args[-1]
        calls.append(endpoint)
        if endpoint.endswith("/pulls/123/comments"):
            return [
                _comment(comment_id=201, body="root", created_at="2026-04-20T10:00:00Z")
            ]
        if endpoint.endswith("/pulls/123/reviews"):
            return [{"id": 42}]
        if endpoint.endswith("/pulls/123/reviews/42/comments"):
            return [
                _comment(
                    comment_id=202,
                    body="fixing: review endpoint reply",
                    created_at="2026-04-20T10:01:00Z",
                    user="jsmithpkp21",
                    in_reply_to_id=201,
                )
            ]
        return []

    monkeypatch.setattr(
        "scripts.pr_review_helper._run_gh_json_paginated", fake_paginated
    )

    comments = _fetch_all_review_comments("owner/repo", 123)

    assert {int(comment["id"]) for comment in comments} == {201, 202}
    assert calls == [
        "repos/owner/repo/pulls/123/comments",
        "repos/owner/repo/pulls/123/reviews",
        "repos/owner/repo/pulls/123/reviews/42/comments",
    ]
