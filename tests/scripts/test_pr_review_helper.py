from __future__ import annotations

from scripts.pr_review_helper import summarize_review_threads


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
