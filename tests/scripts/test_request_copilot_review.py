from __future__ import annotations

import json
import subprocess

import pytest

from scripts.request_copilot_review import (
    _ensure_gh_auth,
    _existing_kickoff_matches,
    _fetch_issue_comments,
    _run_gh,
)


def _cp(stdout_obj: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps(stdout_obj),
        stderr="",
    )


def test_fetch_issue_comments_paginates_until_short_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run_gh(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        del check
        calls.append(args)
        endpoint = args[1]
        if endpoint.endswith("page=1"):
            # Full page keeps pagination going.
            return _cp([{"id": i, "body": f"c{i}"} for i in range(100)])
        if endpoint.endswith("page=2"):
            # Short page ends pagination.
            return _cp([{"id": 1000, "body": "last"}])
        raise AssertionError(f"unexpected endpoint: {endpoint}")

    monkeypatch.setattr("scripts.request_copilot_review._run_gh", fake_run_gh)
    comments = _fetch_issue_comments("owner/repo", 123)
    assert len(comments) == 101
    assert comments[-1]["id"] == 1000
    assert calls == [
        ("api", "repos/owner/repo/issues/123/comments?per_page=100&page=1"),
        ("api", "repos/owner/repo/issues/123/comments?per_page=100&page=2"),
    ]


def test_existing_kickoff_matches_detects_marker_without_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.request_copilot_review._fetch_issue_comments",
        lambda _repo, _pr: [
            {
                "id": 1,
                "body": "@copilot review\n\nAuto-kickoff after push `abc1234`.",
            }
        ],
    )
    assert (
        _existing_kickoff_matches(
            repo="owner/repo",
            pr=123,
            expected_body="@copilot review",
            short_sha="",
        )
        is True
    )


def test_existing_kickoff_matches_detects_plain_kickoff_without_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.request_copilot_review._fetch_issue_comments",
        lambda _repo, _pr: [{"id": 2, "body": "@copilot review"}],
    )
    assert (
        _existing_kickoff_matches(
            repo="owner/repo",
            pr=123,
            expected_body="@copilot review",
            short_sha="",
        )
        is True
    )


def test_existing_kickoff_matches_ignores_other_sha_when_sha_is_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.request_copilot_review._fetch_issue_comments",
        lambda _repo, _pr: [
            {
                "id": 3,
                "body": "@copilot review\n\nAuto-kickoff after push `abc1234`.",
            }
        ],
    )
    assert (
        _existing_kickoff_matches(
            repo="owner/repo",
            pr=123,
            expected_body="@copilot review\n\nAuto-kickoff after push `def5678`.",
            short_sha="def5678",
        )
        is False
    )


def test_ensure_gh_auth_raises_with_remediation_when_unauthenticated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = subprocess.CompletedProcess(
        args=["gh", "auth", "status"],
        returncode=1,
        stdout="",
        stderr="authentication failed",
    )
    monkeypatch.setattr(
        "scripts.request_copilot_review._run_gh", lambda *_args, **_kwargs: status
    )
    with pytest.raises(RuntimeError, match="gh auth login"):
        _ensure_gh_auth()


def test_run_gh_raises_runtime_error_with_stderr_stdout_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "api", "repos/owner/repo/issues/123/comments"],
            stderr="api denied",
            output="partial output",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="GitHub command failed") as exc_info:
        _run_gh("api", "repos/owner/repo/issues/123/comments")

    msg = str(exc_info.value)
    assert "stderr: api denied" in msg
    assert "stdout: partial output" in msg
