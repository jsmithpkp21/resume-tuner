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


# ---------------------------------------------------------------------------
# Error-tolerance: partial captures, missing files, bad JSON
# ---------------------------------------------------------------------------


def test_replay_skips_invalid_json_capture_and_continues(
    answer_bank: dict[str, object], tmp_path: Path
) -> None:
    """A truncated/garbled fields-*.json doesn't crash the whole replay run."""
    bad = tmp_path / "fields-broken-1.json"
    bad.write_text("{not valid json")
    good = tmp_path / "fields-good-2.json"
    good.write_text(
        json.dumps(
            [
                {
                    "url": "u",
                    "ts": 1,
                    "fields": [{"label": "First Name*", "type": "text"}],
                }
            ]
        )
    )
    buf = io.StringIO()
    n = replay(answer_bank=answer_bank, capture_paths=[bad, good], out=buf)
    output = buf.getvalue()
    # Bad capture is logged as skipped with the parse error reason
    assert "skipped: fields-broken-1.json is not valid JSON" in output
    # Good capture still produced its one match
    assert n == 1
    assert "=== good " in output


def test_replay_skips_missing_capture_file_via_oserror(
    answer_bank: dict[str, object], tmp_path: Path
) -> None:
    """An OSError on a missing/unreadable file produces a graceful skip line."""
    missing = tmp_path / "fields-missing-1.json"  # not created
    buf = io.StringIO()
    n = replay(answer_bank=answer_bank, capture_paths=[missing], out=buf)
    assert n == 0
    assert "=== missing ===" in buf.getvalue() or "=== missing" in buf.getvalue()


def test_replay_slug_without_trailing_timestamp_is_left_unchanged(
    answer_bank: dict[str, object], tmp_path: Path
) -> None:
    """When the trailing token isn't all digits, the slug stays intact."""
    cap = tmp_path / "fields-no-ts-here.json"
    cap.write_text(
        json.dumps(
            [
                {
                    "url": "u",
                    "ts": 1,
                    "fields": [{"label": "First Name*", "type": "text"}],
                }
            ]
        )
    )
    buf = io.StringIO()
    replay(answer_bank=answer_bank, capture_paths=[cap], out=buf)
    # No trailing-numeric strip — full "no-ts-here" should appear as the slug
    assert "=== no-ts-here " in buf.getvalue()


# ---------------------------------------------------------------------------
# _main CLI surface
# ---------------------------------------------------------------------------


def test_main_cli_reads_bank_and_invokes_replay(
    answer_bank: dict[str, object], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`_main` parses --bank + capture paths and runs end-to-end without error."""
    from job_apply_kit.match_replay import _main

    # Write a real TOML answer bank that mirrors the fixture
    bank_path = tmp_path / "bank.toml"
    bank_path.write_text(
        """
[name]
first = "Jane"
last = "Doe"
synonyms = ["first name", "first name*", "last name", "last name*"]

[contact]
email = "jane@example.com"
synonyms = ["email", "email address*"]
""",
        encoding="utf-8",
    )

    cap = tmp_path / "fields-cli-1700000000.json"
    cap.write_text(
        json.dumps(
            [
                {
                    "url": "u",
                    "ts": 1,
                    "fields": [
                        {"label": "First Name*", "type": "text"},
                        {"label": "Email Address*", "type": "email"},
                    ],
                }
            ]
        )
    )

    rc = _main(["--bank", str(bank_path), str(cap)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "=== cli " in captured.out
    assert "OVERALL" in captured.out


def test_main_cli_verbose_flag_logs_per_label_decisions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--verbose` surfaces per-label match/skip lines on stdout."""
    from job_apply_kit.match_replay import _main

    bank_path = tmp_path / "bank.toml"
    bank_path.write_text(
        """
[name]
first = "Jane"
synonyms = ["first name", "first name*"]
""",
        encoding="utf-8",
    )
    cap = tmp_path / "fields-v-1.json"
    cap.write_text(
        json.dumps(
            [
                {
                    "url": "u",
                    "ts": 1,
                    "fields": [
                        {"label": "First Name*", "type": "text"},
                        {"label": "Mystery Field*", "type": "text"},
                    ],
                }
            ]
        )
    )

    rc = _main(["--bank", str(bank_path), "--verbose", str(cap)])
    out = capsys.readouterr().out
    assert rc == 0
    # Verbose lines for both labels
    assert "First Name*" in out
    assert "Mystery Field*" in out


def test_main_cli_rejects_blocked_runtime_bank(tmp_path: Path) -> None:
    """`_main` rejects a `--bank` path under a blocked runtime root."""
    from job_apply_kit.match_replay import _main

    # Use the real repo sandbox/ root — it's the canonical blocked path.
    repo_root = Path(__file__).resolve().parents[2]
    blocked_bank = repo_root / "sandbox" / "bank.toml"
    cap = tmp_path / "fields-x-1.json"
    cap.write_text("[]")
    with pytest.raises(ValueError, match="blocked runtime"):
        _main(["--bank", str(blocked_bank), str(cap)])


def test_main_cli_rejects_blocked_runtime_capture_file(tmp_path: Path) -> None:
    """`_main` rejects a positional capture path under a blocked runtime root.

    The bank guard and the per-file guard are independent loops in `_main`;
    this test pins the per-file guard so a future regression that removes
    only the file-side check is still caught.
    """
    from job_apply_kit.match_replay import _main

    # Safe bank in tmp_path, blocked capture path under repo sandbox/.
    repo_root = Path(__file__).resolve().parents[2]
    bank_path = tmp_path / "bank.toml"
    bank_path.write_text(
        '[name]\nfirst = "Jane"\nsynonyms = ["first name"]\n',
        encoding="utf-8",
    )
    blocked_cap = repo_root / "sandbox" / "fields-blocked-1.json"
    with pytest.raises(ValueError, match="blocked runtime"):
        _main(["--bank", str(bank_path), str(blocked_cap)])
