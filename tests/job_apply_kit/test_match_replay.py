"""Tests for `job_apply_kit.match_replay`.

The replay tool reads captured `fields-*.json` files and runs the matcher
against an answer bank. These tests exercise the function-level API with a
synthetic capture fixture (no Playwright, no live browser, no real apply
sites) so they run unconditionally and finish in milliseconds.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from job_apply_kit import replay


@pytest.fixture
def answer_bank() -> dict[str, object]:
    """A minimal bank covering match / empty-value / no-match outcomes."""
    return {
        "name": {
            "first": "Jane",
            "last": "Doe",
            "synonyms": ["first name", "first name*", "last name", "last name*"],
        },
        "contact": {
            "email": "jane@example.com",
            "synonyms": ["email", "email address*"],
        },
        "preferences": {
            "salary_expectation_usd": "",  # TODO blank → empty-value outcome
            "synonyms": ["salary", "salary expectation"],
        },
    }


@pytest.fixture
def fields_capture(tmp_path: Path) -> Path:
    """Synthetic capture: matches + skip-no-match + skip-empty-value + skip-honeypot."""
    capture = [
        {
            "url": "https://example.com/apply",
            "ts": 1700000000,
            "fields": [
                {"label": "First Name*", "type": "text"},
                {"label": "Last Name*", "type": "text"},
                {"label": "Email Address*", "type": "email"},
                {"label": "Salary Expectation", "type": "text"},  # matched but empty
                {"label": "Job Title*", "type": "text"},  # no-match (structural)
                {
                    # Honeypot pattern — substring match
                    "label": (
                        "Enter website. This input is for robots only, "
                        "do not enter if you're human."
                    ),
                    "type": "text",
                },
                {"label": "", "type": "text"},  # empty label — skipped silently
            ],
        }
    ]
    path = tmp_path / "fields-test-1700000000.json"
    path.write_text(json.dumps(capture))
    return path


def test_replay_returns_match_count(
    answer_bank: dict[str, object], fields_capture: Path
) -> None:
    buf = io.StringIO()
    n = replay(answer_bank=answer_bank, capture_paths=[fields_capture], out=buf)
    # First Name, Last Name, Email — 3 matches; Salary is empty-value not match;
    # Job Title is no-match; honeypot is skip[honeypot]; empty label not counted.
    assert n == 3


def test_replay_summary_includes_all_skip_reasons(
    answer_bank: dict[str, object], fields_capture: Path
) -> None:
    buf = io.StringIO()
    replay(answer_bank=answer_bank, capture_paths=[fields_capture], out=buf)
    output = buf.getvalue()
    # Every observed outcome reason should appear in the summary
    assert "matched" in output
    assert "honeypot" in output
    assert "no-match" in output
    assert "empty-value" in output


def test_replay_verbose_mode_logs_per_label_decisions(
    answer_bank: dict[str, object], fields_capture: Path
) -> None:
    buf = io.StringIO()
    replay(
        answer_bank=answer_bank,
        capture_paths=[fields_capture],
        verbose=True,
        out=buf,
    )
    output = buf.getvalue()
    # Each captured label should show up in a verbose decision line
    assert "First Name*" in output
    assert "Job Title*" in output
    # Honeypot line is still printed (with the skip marker)
    assert "robots only" in output


def test_replay_dedupes_labels_within_session(
    answer_bank: dict[str, object], tmp_path: Path
) -> None:
    # Multiple snapshots, same field repeated 5×, should count as 1 distinct label
    capture = [
        {"url": "u", "ts": i, "fields": [{"label": "First Name*", "type": "text"}]}
        for i in range(5)
    ]
    path = tmp_path / "fields-dedup-1700000000.json"
    path.write_text(json.dumps(capture))
    buf = io.StringIO()
    n = replay(answer_bank=answer_bank, capture_paths=[path], out=buf)
    assert n == 1
    # And the per-session line should say "1 distinct labels"
    assert "1 distinct labels" in buf.getvalue()


def test_replay_handles_multiple_captures(
    answer_bank: dict[str, object], tmp_path: Path
) -> None:
    cap1 = tmp_path / "fields-a-1.json"
    cap1.write_text(
        json.dumps(
            [
                {
                    "url": "u1",
                    "ts": 1,
                    "fields": [{"label": "First Name*", "type": "text"}],
                }
            ]
        )
    )
    cap2 = tmp_path / "fields-b-2.json"
    cap2.write_text(
        json.dumps(
            [{"url": "u2", "ts": 2, "fields": [{"label": "Email", "type": "email"}]}]
        )
    )
    buf = io.StringIO()
    n = replay(answer_bank=answer_bank, capture_paths=[cap1, cap2], out=buf)
    assert n == 2  # one match per capture
    output = buf.getvalue()
    # Per-session headers should both appear
    assert "=== a " in output
    assert "=== b " in output
