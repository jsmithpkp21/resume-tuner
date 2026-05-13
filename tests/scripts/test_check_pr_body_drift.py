"""Tests for `scripts/check_pr_body_drift.py`.

Strategy: exercise the pure `scan_body` function directly (no
subprocess, no `gh`) and the `_format_report` formatter. The
`_fetch_pr_body` / `_gh_preflight` paths are exercised via
monkeypatch in a minimal way — we don't actually call `gh`, we
inject canned responses through subprocess.run.

Pulls the script in via `importlib.util` (no `sys.path` mutation),
matching the pattern established by `test_check_doc_drift.py`.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_pr_body_drift.py"
_spec = importlib.util.spec_from_file_location("check_pr_body_drift", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_pr_body_drift = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_pr_body_drift)


class TestScanBody:
    """`scan_body` is the pure-function core. No I/O, no subprocess."""

    def test_clean_body_returns_no_hits(self) -> None:
        body = "## Summary\n\nThis PR adds Locator.fill support.\n"
        assert check_pr_body_drift.scan_body(body) == []

    def test_single_drift_phrase_caught(self) -> None:
        body = "## Summary\n\nUses page.fill() under the hood.\n"
        hits = check_pr_body_drift.scan_body(body)
        assert len(hits) == 1
        lineno, matched, hint = hits[0]
        assert lineno == 3
        assert matched == "page.fill"
        assert "Locator.fill" in hint  # remediation hint mentions correct API

    def test_multiple_drift_phrases_each_caught(self) -> None:
        body = (
            "## What changed\n"
            "\n"
            "Replaces page.fill with Locator.fill.\n"
            "Same for page.click.\n"
        )
        hits = check_pr_body_drift.scan_body(body)
        # 2 hits — page.fill on line 3, page.click on line 4.
        assert len(hits) == 2
        assert [h[0] for h in hits] == [3, 4]
        assert {h[1] for h in hits} == {"page.fill", "page.click"}

    def test_opt_out_marker_skips_line(self) -> None:
        body = (
            "Quoting the deny-list: page.fill, page.click.  # noqa: doc-drift\n"
            "Real drift: page.select_option here.\n"
        )
        hits = check_pr_body_drift.scan_body(body)
        # Line 1 has opt-out → skipped despite 2 deny-list phrases.
        # Line 2 has no opt-out → 1 hit.
        assert len(hits) == 1
        assert hits[0] == (
            2,
            "page.select_option",
            check_pr_body_drift.scan_body.__globals__[
                "_load_drift_module"
            ]()._DENY_PATTERNS[2][1],
        )

    def test_empty_body_returns_no_hits(self) -> None:
        assert check_pr_body_drift.scan_body("") == []

    def test_word_boundary_protects_partial_matches(self) -> None:
        # `homepage.fill_in_form()` shouldn't trip `page.fill` —
        # the deny-list patterns use `\b` boundaries.
        body = "This calls homepage.fill_in_form() but not the bad one.\n"
        assert check_pr_body_drift.scan_body(body) == []


class TestFormatReport:
    """The formatter is pure; tests assert exact wording so future
    edits don't silently change the operator-facing UX."""

    def test_report_contains_count_and_per_line_diagnostics(self) -> None:
        hits = [
            (3, "page.fill", "use Locator.fill"),
            (7, "page.click", "use Locator.click"),
        ]
        out = check_pr_body_drift._format_report(hits, "noqa: doc-drift")
        assert "2 stale API reference(s)" in out
        assert "body line 3: `page.fill` — use Locator.fill" in out
        assert "body line 7: `page.click` — use Locator.click" in out
        assert "noqa: doc-drift" in out
        assert "gh pr edit --body" in out


class TestMainExitCodes:
    """End-to-end via `main`, with `_fetch_pr_body` monkeypatched so
    we don't actually call `gh`."""

    def test_clean_body_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            check_pr_body_drift,
            "_fetch_pr_body",
            lambda pr: "## Summary\n\nClean body.\n",
        )
        assert check_pr_body_drift.main([]) == 0

    def test_drift_body_exits_one(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            check_pr_body_drift,
            "_fetch_pr_body",
            lambda pr: "Uses page.fill under the hood.\n",
        )
        rc = check_pr_body_drift.main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "page.fill" in captured.err

    def test_empty_body_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Auto-generated PRs sometimes have blank descriptions —
        # don't fail on that, treat as nothing-to-scan.
        monkeypatch.setattr(check_pr_body_drift, "_fetch_pr_body", lambda pr: "")
        assert check_pr_body_drift.main([]) == 0

    def test_pr_number_passed_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The first positional arg should reach _fetch_pr_body.
        seen: list[str | None] = []

        def fake_fetch(pr: str | None) -> str:
            seen.append(pr)
            return ""

        monkeypatch.setattr(check_pr_body_drift, "_fetch_pr_body", fake_fetch)
        check_pr_body_drift.main(["368"])
        assert seen == ["368"]


class TestGhPreflight:
    """`_gh_preflight` is the AGENTS.md-mandated check; missing-binary
    + auth-failure paths produce clean exits, not tracebacks."""

    def test_missing_gh_binary_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def raise_fnf(*args: object, **kwargs: object) -> None:
            raise FileNotFoundError("gh")

        monkeypatch.setattr(subprocess, "run", raise_fnf)
        with pytest.raises(SystemExit) as exc_info:
            check_pr_body_drift._gh_preflight()
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "`gh` CLI not found" in err

    def test_auth_failure_exits_two(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def fake_run(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["gh", "auth", "status"],
                returncode=1,
                stdout="",
                stderr="not logged in",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as exc_info:
            check_pr_body_drift._gh_preflight()
        assert exc_info.value.code == 2
        err = capsys.readouterr().err
        assert "gh auth status" in err
        assert "not logged in" in err

    def test_auth_ok_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["gh", "auth", "status"],
                returncode=0,
                stdout="ok",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        # No exception, no SystemExit.
        assert check_pr_body_drift._gh_preflight() is None
