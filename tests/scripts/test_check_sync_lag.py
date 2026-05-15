"""Tests for `scripts/check_sync_lag.py`.

Five parts to cover:
  1. `_parse_version` — stdlib semver-ish parser.
  2. `compare_versions(pinned, latest)` — pure (exit_code, message)
     contract.
  3. `_read_pinned_version()` + `_repo_slug_from_tooling_toml()` — TOML
     parsers; tested via monkeypatch on the module's `TOOLING_TOML`
     constant.
  4. `_fetch_latest_tag(repo)` / `_gh_preflight()` — subprocess shells
     to `gh`; tested by monkeypatching `subprocess.run`.
  5. End-to-end exit-code paths via the same monkeypatch.

Loaded via `importlib.util` (no `sys.path` mutation), matching the
pattern in `test_check_doc_drift.py` and the other sibling check tests.
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


class TestParseVersion:
    """`_parse_version` is the strict stdlib semver-ish parser."""

    def test_basic_v_prefix(self) -> None:
        assert check_sync_lag._parse_version("v1.2.3") == (1, 2, 3)

    def test_no_v_prefix(self) -> None:
        assert check_sync_lag._parse_version("1.2.3") == (1, 2, 3)

    def test_capital_v_prefix(self) -> None:
        assert check_sync_lag._parse_version("V1.2.3") == (1, 2, 3)

    def test_zero_components(self) -> None:
        assert check_sync_lag._parse_version("v0.0.0") == (0, 0, 0)

    def test_multi_digit_components(self) -> None:
        assert check_sync_lag._parse_version("v12.34.567") == (12, 34, 567)

    def test_rejects_double_v(self) -> None:
        # Pre-fix bug in the consumer prototype: `lstrip("v")` silently
        # accepted `vv1.2.3` by stripping both v's. The strict regex
        # requires at most one optional `v`. (See
        # feedback_check_parser_before_normalizing.md.)
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("vv1.2.3")

    def test_rejects_two_components(self) -> None:
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("v1.2")

    def test_rejects_four_components(self) -> None:
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("v1.2.3.4")

    def test_rejects_pre_release_suffix(self) -> None:
        # Tooling tags are clean vX.Y.Z; pre-release suffixes
        # (`-rc1`, `+abc`) are intentionally unsupported and fail
        # cleanly rather than being silently coerced.
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("v1.2.3-rc1")

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("garbage")

    def test_rejects_empty_v(self) -> None:
        with pytest.raises(ValueError):
            check_sync_lag._parse_version("v")


class TestCompareVersions:
    """Public-ish `compare_versions(pinned, latest)` contract."""

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

    def test_double_v_prefix_rejected(self) -> None:
        # Defense-in-depth: even if a future refactor of `_parse_version`
        # reintroduces the `lstrip` bug from the consumer prototype,
        # `vv1.2.3` must still return cannot-parse not silently-normalized.
        code, msg = check_sync_lag.compare_versions("vv1.2.3", "v1.32.1")
        assert code == 2
        assert "cannot parse" in msg


class TestBranchRefHandling:
    """README documents branch refs as a supported
    `tooling.toml.version` channel; the tooling repo's own
    `project-template/tooling.toml` uses `version = "main"`. Branch
    pins must NOT trigger exit 2 — they're a category mismatch with
    tag comparison, not a parse failure.

    Under the conservative detection rule, "branch ref" means EITHER:
    the value contains `/` (impossible in a release tag, so
    `release/stable` / `feature/420` qualify), OR the value matches a
    known branch name (`main`, `master`, `develop`, `trunk`, `HEAD`).
    Other unrecognized strings stay on the cannot-parse exit-2 path
    so the operator gets an actionable error rather than silent
    branch-ref treatment of a typo. (PR #429 review.)
    """

    def test_main_branch_returns_tracking_zero(self) -> None:
        code, msg = check_sync_lag.compare_versions("main", "v1.32.1")
        assert code == 0
        assert "tracking branch" in msg
        # Still surfaces the latest tag so the operator can decide.
        assert "v1.32.1" in msg
        assert "main" in msg

    def test_release_stable_branch_returns_tracking_zero(self) -> None:
        code, msg = check_sync_lag.compare_versions("release/stable", "v1.32.1")
        assert code == 0
        assert "tracking branch" in msg
        assert "release/stable" in msg

    def test_feature_branch_returns_tracking_zero(self) -> None:
        code, msg = check_sync_lag.compare_versions("feature/420", "v1.32.1")
        assert code == 0
        assert "tracking branch" in msg

    def test_branch_ref_with_no_tag_components_still_handled(self) -> None:
        # A bare branch name with no slashes.
        code, _ = check_sync_lag.compare_versions("develop", "v1.32.1")
        assert code == 0

    def test_malformed_tag_still_returns_cannot_parse(self) -> None:
        # The branch detector must NOT capture malformed-tag shapes.
        # `v1.2` has no letters / slashes and fails the tag regex,
        # so it stays in the exit-2 cannot-parse path.
        code, msg = check_sync_lag.compare_versions("v1.2", "v1.32.1")
        assert code == 2
        assert "cannot parse" in msg

    def test_pre_release_tag_returns_cannot_parse(self) -> None:
        # `v1.2.3-rc1` is a malformed-tag shape (pre-release suffix
        # unsupported). Under the conservative branch-ref rule it
        # has no `/` and isn't a known branch name, so it stays on
        # the cannot-parse exit-2 path with an actionable error
        # rather than getting silently treated as a branch.
        code, msg = check_sync_lag.compare_versions("v1.2.3-rc1", "v1.32.1")
        assert code == 2
        assert "cannot parse" in msg

    def test_branch_ref_with_garbage_latest_returns_2(self) -> None:
        # Pre-fix bug: the branch-ref shortcut returned (0, "...") before
        # `latest` was parsed, so `compare_versions("main", "garbage")`
        # returned exit 0 with the garbage tag embedded in the message —
        # masking a real upstream-tag problem. Now `latest` is validated
        # first so malformed `latest` fails closed regardless of whether
        # `pinned` is a branch ref. (tooling#446.)
        code, msg = check_sync_lag.compare_versions("main", "garbage")
        assert code == 2
        assert "cannot parse latest version" in msg

    def test_branch_ref_with_malformed_tag_latest_returns_2(self) -> None:
        # Same as above but `latest` is tag-shaped-but-incomplete
        # (`v1.2` is two components, not three). Still must fail closed.
        code, msg = check_sync_lag.compare_versions("release/stable", "v1.2")
        assert code == 2
        assert "cannot parse latest version" in msg


class TestIsBranchRef:
    """`_is_branch_ref` conservative sniff: returns True only when the
    value (a) contains `/` (impossible in a release tag) or (b)
    matches a known branch name (`main`, `master`, `develop`, `trunk`,
    `HEAD`). Other unrecognized strings (`v1.2`, `vv1.2.3`,
    `not-a-version`) return False so the caller hands them to the
    strict parser and they take the cannot-parse exit-2 path."""

    def test_main_is_branch(self) -> None:
        assert check_sync_lag._is_branch_ref("main") is True

    def test_release_stable_is_branch(self) -> None:
        assert check_sync_lag._is_branch_ref("release/stable") is True

    def test_feature_slash_is_branch(self) -> None:
        assert check_sync_lag._is_branch_ref("feature/420-something") is True

    def test_tag_is_not_branch(self) -> None:
        assert check_sync_lag._is_branch_ref("v1.32.1") is False
        assert check_sync_lag._is_branch_ref("1.32.1") is False

    def test_malformed_tag_is_not_branch(self) -> None:
        # `v1.2` has only digits + dots + `v` → not a branch.
        # Caller falls through to the strict parser and gets exit 2.
        assert check_sync_lag._is_branch_ref("v1.2") is False
        assert check_sync_lag._is_branch_ref("1.2") is False


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
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "git@github.com:acme/tooling.git"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_http_scheme_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "http://github.com/acme/tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_extra_path_segments_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling/tree/main"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_path_traversal_owner_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/../tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_dot_only_owner_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/./tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_query_string_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # urlparse puts `?tab=readme` in parsed.query, NOT parsed.path,
        # so the slug regex would accept `acme/tooling` without an
        # explicit query check. (PR #429 review.)
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling?tab=readme"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_fragment_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Fragments live in parsed.fragment, also outside parsed.path.
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com/acme/tooling#anchor"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_userinfo_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `user:pass@host` keeps userinfo separate from hostname. The
        # README documents bare `https://github.com/<owner>/<name>` so
        # any userinfo is a category mismatch.
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://user:pass@github.com/acme/tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_non_default_port_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com:8443/acme/tooling"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", toml)
        assert check_sync_lag._repo_slug_from_tooling_toml() == "jsmithpkp21/tooling"

    def test_malformed_port_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # `parsed.port` raises ValueError on non-numeric port text.
        # Without the try/except wrap, this would crash the script
        # with a traceback instead of returning the default slug.
        # (tooling#432.)
        toml = tmp_path / "tooling.toml"
        toml.write_text(
            'version = "v1.32.1"\nrepo = "https://github.com:abc/acme/tooling"\n',
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

    def test_symlink_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # SECURITY guard: a symlink at TOOLING_TOML must fail closed
        # before any read. Matches scripts/validate_tooling_toml_drift.py.
        # (PR #429 review.)
        real = tmp_path / "real.toml"
        real.write_text('version = "v1.0.0"\n', encoding="utf-8")
        link = tmp_path / "tooling.toml"
        link.symlink_to(real)
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", link)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2
        assert "SECURITY" in capsys.readouterr().err

    def test_broken_symlink_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Path.exists() follows symlinks, so a broken symlink would be
        # reported as "missing" and skip the SECURITY guard without the
        # is_symlink() check ordered first.
        link = tmp_path / "tooling.toml"
        link.symlink_to(tmp_path / "does-not-exist")
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", link)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2
        assert "SECURITY" in capsys.readouterr().err

    def test_directory_rejected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Regular-file guard: a directory at TOOLING_TOML would let
        # the script attempt to open it and produce a confusing IsADirectoryError
        # traceback. Stand-in for the FIFO/device case (FIFOs require
        # OS-specific mkfifo; the is_file() guard catches all three).
        d = tmp_path / "tooling.toml"
        d.mkdir()
        monkeypatch.setattr(check_sync_lag, "TOOLING_TOML", d)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag._read_pinned_version()
        assert exc.value.code == 2
        assert "MALFORMED" in capsys.readouterr().err


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
        calls: list[Any] = []

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
        assert len(calls) == 2  # preflight + api fetch

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


class TestMain:
    """End-to-end wiring tests. Monkeypatch the three I/O boundaries
    (`_read_pinned_version`, `_repo_slug_from_tooling_toml`,
    `_fetch_latest_tag`) and assert that `main()` returns the right
    exit code and routes output to stdout vs stderr correctly. A
    regression in output routing, remediation text, or the final
    exit-code wiring would slip past the unit tests on the pure
    helpers. (PR #429 review.)
    """

    @staticmethod
    def _wire(
        monkeypatch: pytest.MonkeyPatch,
        *,
        pinned: str,
        latest: str,
        repo: str = "jsmithpkp21/tooling",
    ) -> None:
        monkeypatch.setattr(check_sync_lag, "_read_pinned_version", lambda: pinned)
        monkeypatch.setattr(
            check_sync_lag, "_repo_slug_from_tooling_toml", lambda: repo
        )
        monkeypatch.setattr(check_sync_lag, "_fetch_latest_tag", lambda r: latest)

    def test_up_to_date_returns_0_and_writes_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(monkeypatch, pinned="v1.32.1", latest="v1.32.1")
        code = check_sync_lag.main()
        out, err = capsys.readouterr()
        assert code == 0
        assert "up-to-date" in out
        assert err == ""

    def test_ahead_of_release_returns_0_and_writes_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(monkeypatch, pinned="v1.33.0", latest="v1.32.1")
        code = check_sync_lag.main()
        out, err = capsys.readouterr()
        assert code == 0
        assert "ahead of release" in out
        assert err == ""

    def test_tracking_branch_returns_0_and_writes_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # README-documented case: pinned to `main`. Must exit 0 and
        # surface the latest tag without any remediation noise on stderr.
        self._wire(monkeypatch, pinned="main", latest="v1.32.1")
        code = check_sync_lag.main()
        out, err = capsys.readouterr()
        assert code == 0
        assert "tracking branch" in out
        assert "v1.32.1" in out
        assert err == ""

    def test_behind_returns_1_with_remediation_on_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(
            monkeypatch,
            pinned="v1.30.0",
            latest="v1.32.1",
            repo="jsmithpkp21/tooling",
        )
        code = check_sync_lag.main()
        out, err = capsys.readouterr()
        assert code == 1
        assert out == ""
        # Diagnostic message:
        assert "behind by minor version" in err
        # Actionable remediation: bump instructions + release notes URL:
        assert "Bump `version` in tooling.toml" in err
        assert "make sync-tooling" in err
        assert "https://github.com/jsmithpkp21/tooling/releases/tag/v1.32.1" in err

    def test_behind_patch_level_shows_patch_in_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(monkeypatch, pinned="v1.32.0", latest="v1.32.1")
        code = check_sync_lag.main()
        _, err = capsys.readouterr()
        assert code == 1
        assert "behind by patch version" in err

    def test_behind_major_level_shows_major_in_message(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        self._wire(monkeypatch, pinned="v1.99.99", latest="v2.0.0")
        code = check_sync_lag.main()
        _, err = capsys.readouterr()
        assert code == 1
        assert "behind by major version" in err

    def test_cannot_parse_returns_2_with_no_remediation(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Malformed-tag pinned (not a branch ref): exit 2, message on
        # stderr, and importantly NO "Bump version" remediation — that
        # text only makes sense for the behind-by-N case.
        self._wire(monkeypatch, pinned="v1.2", latest="v1.32.1")
        code = check_sync_lag.main()
        out, err = capsys.readouterr()
        assert code == 2
        assert out == ""
        assert "cannot parse" in err
        assert "Bump `version`" not in err

    def test_main_propagates_systemexit_from_read_pinned_version(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # If the TOML readers fail they `sys.exit(2)` directly; main()
        # must NOT swallow that.
        def boom() -> str:
            raise SystemExit(2)

        monkeypatch.setattr(check_sync_lag, "_read_pinned_version", boom)
        with pytest.raises(SystemExit) as exc:
            check_sync_lag.main()
        assert exc.value.code == 2
