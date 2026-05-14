"""Tests for `scripts/check_sync_lag.py`.

The script has three parts:
  1. `compare_versions(pinned, latest)` — pure semver comparison.
  2. `_read_pinned_version()` + `_repo_slug_from_tooling_toml()` — TOML
     parsers; tested via monkeypatch on the module's `TOOLING_TOML`
     constant.
  3. `_fetch_latest_tag(repo)` / `_gh_preflight()` — subprocess shells
     to `gh`; tested by monkeypatching `subprocess.run`.

Loaded via `importlib.util` (no `sys.path` mutation), matching the
pattern in `test_check_doc_drift.py` and friends.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_sync_lag.py"
_spec = importlib.util.spec_from_file_location("check_sync_lag", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
check_sync_lag = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_sync_lag)


class TestCompareVersions:
    """Pure-function semver compare. Handles `v` prefix + level diff."""

    def test_equal_returns_zero(self) -> None:
        code, msg = check_sync_lag.compare_versions("v1.2.3", "v1.2.3")
        assert code == 0
        assert "up-to-date" in msg

    def test_equal_without_v_prefix(self) -> None:
        code, _ = check_sync_lag.compare_versions("1.2.3", "1.2.3")
        assert code == 0

    def test_mixed_v_prefix_normalizes(self) -> None:
        code, _ = check_sync_lag.compare_versions("v1.2.3", "1.2.3")
        assert code == 0

    def test_patch_behind(self) -> None:
        code, msg = check_sync_lag.compare_versions("v1.32.0", "v1.32.1")
        assert code == 1
        assert "patch" in msg
        assert "v1.32.0" in msg
        assert "v1.32.1" in msg

    def test_minor_behind(self) -> None:
        code, msg = check_sync_lag.compare_versions("v1.31.0", "v1.32.0")
        assert code == 1
        assert "minor" in msg

    def test_major_behind(self) -> None:
        code, msg = check_sync_lag.compare_versions("v1.99.99", "v2.0.0")
        assert code == 1
        assert "major" in msg

    def test_ahead_of_release(self) -> None:
        # Consumer testing a release candidate ahead of the latest tag.
        code, msg = check_sync_lag.compare_versions("v2.0.0", "v1.32.1")
        assert code == 0
        assert "ahead" in msg

    def test_unparseable_pinned(self) -> None:
        code, msg = check_sync_lag.compare_versions("not-a-version", "v1.32.1")
        assert code == 2
        assert "cannot parse" in msg

    def test_unparseable_latest(self) -> None:
        code, msg = check_sync_lag.compare_versions("v1.32.0", "garbage")
        assert code == 2


class TestRepoSlugParser:
    """`_repo_slug_from_tooling_toml()` extracts owner/name from the
    `repo` URL, defaulting to `jsmithpkp21/tooling` on any failure."""

    def test_https_url_with_git_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling.git"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "acme/tooling"

    def test_https_url_no_git_suffix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "acme/tooling"

    def test_missing_repo_key_returns_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text('version = "v1.32.1"\n', encoding="utf-8")
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_non_github_url_returns_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://gitlab.example.com/x/y"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_host_substring_match_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-fix bug: `"github.com" in url` substring check accepted
        # any URL that happened to contain the literal "github.com",
        # including `https://notgithub.com/...`. The strict urlparse
        # form checks hostname equality and rejects this. (PR #392 r1.)
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://notgithub.com/acme/tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_ssh_url_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pre-fix bug: SSH URL `git@github.com:acme/tooling.git` passed
        # the substring check but the `split("github.com/", ...)` parse
        # returned the whole string. The strict urlparse form requires
        # http(s) scheme and rejects SSH. (PR #392 r1.)
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "git@github.com:acme/tooling.git"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_extra_path_segments_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # GitHub URLs with deep paths (e.g. `/owner/name/tree/main`)
        # should NOT be parsed as `owner/name/tree/main` — the strict
        # slug regex catches that and falls back to default rather
        # than passing a malformed slug to `gh api`. (PR #392 r1.)
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling/tree/main"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"


class TestReadPinnedVersion:
    def test_returns_pinned(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text('version = "v1.32.0"\n', encoding="utf-8")
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._read_pinned_version() == "v1.32.0"

    def test_missing_file_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            check_sync_lag, "TOOLING_TOML", tmp_path / "nonexistent.toml"
        )
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2

    def test_malformed_toml_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text("not toml = = = = ]]\n", encoding="utf-8")
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2

    def test_missing_version_key_exits_2(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text('repo = "x"\n', encoding="utf-8")
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2


class TestGhPreflight:
    def test_auth_ok_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["gh", "auth", "status"],
                returncode=0,
                stdout="ok",
                stderr="",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        check_sync_lag._gh_preflight()  # no SystemExit

    def test_missing_gh_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def raise_oserror(*args: Any, **kwargs: Any) -> None:
            raise FileNotFoundError("gh")

        monkeypatch.setattr(subprocess, "run", raise_oserror)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._gh_preflight()
        assert exc.value.code == 2
        assert "gh" in capsys.readouterr().err.lower()

    def test_auth_failure_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=["gh", "auth", "status"],
                returncode=1,
                stdout="",
                stderr="not logged in",
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._gh_preflight()
        assert exc.value.code == 2
        assert "not logged in" in capsys.readouterr().err


class TestFetchLatestTag:
    def test_returns_tag_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # _gh_preflight is called first → return ok.
        # Then `gh api` runs → return tag.
        calls = []

        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0]
            calls.append(cmd)
            if "auth" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="v1.32.1\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert check_sync_lag._fetch_latest_tag("jsmithpkp21/tooling") == "v1.32.1"
        # Two subprocess calls: preflight + api fetch.
        assert len(calls) == 2

    def test_gh_api_failure_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0]
            if "auth" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=1, stdout="", stderr="network error"
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._fetch_latest_tag("jsmithpkp21/tooling")
        assert exc.value.code == 2
        assert "network error" in capsys.readouterr().err

    def test_empty_tag_exits_2(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # `gh api` returns 0 but empty stdout — shouldn't be treated as
        # success.
        def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd = args[0]
            if "auth" in cmd:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout="ok", stderr=""
                )
            return subprocess.CompletedProcess(
                args=cmd, returncode=0, stdout="\n", stderr=""
            )

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._fetch_latest_tag("jsmithpkp21/tooling")
        assert exc.value.code == 2
        assert "empty tag" in capsys.readouterr().err
