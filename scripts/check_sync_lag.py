#!/usr/bin/env python3
"""Report the gap between this repo's pinned tooling version and upstream latest.

Surfaced by resume-builder PR #389 retrospective: 4 of 5 Copilot comments
on that sync PR were already fixed in a newer tooling tag, but the gap
wasn't obvious until I checked manually. This target makes "you're N
patch versions behind" visible at a glance.

Sketched as a consumer-side prototype per the tooling promotion policy
(see jsmithpkp21/tooling#420 for the upstream promotion plan).

Behavior:

  - Reads pinned tooling version from `tooling.toml` `version` key.
  - Calls `gh api repos/<owner>/tooling/releases/latest --jq .tag_name`
    for the upstream latest. Uses the AGENTS.md-mandated `gh auth
    status` preflight.
  - Compares via `packaging.version.Version` (handles `v` prefix +
    semver ordering).
  - Exits:
      0 — pinned == latest (up-to-date) OR pinned > latest (consumer
          ahead of release, e.g. testing a release candidate)
      1 — pinned < latest (behind; surfaces the gap + level)
      2 — cannot determine (gh missing/unauth, network failure,
          malformed tooling.toml)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLING_TOML = REPO_ROOT / "tooling.toml"
_GH_AUTH_CMD = ["gh", "auth", "status"]


def _gh_preflight() -> None:
    """AGENTS.md-mandated `gh auth status` preflight."""
    try:
        proc = subprocess.run(_GH_AUTH_CMD, capture_output=True, text=True, check=False)
    except OSError as e:
        sys.stderr.write(
            f"check-sync-lag: cannot invoke `gh`: {e}\n"
            "Install the GitHub CLI: https://cli.github.com/\n"
        )
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(
            "check-sync-lag: `gh auth status` failed; aborting.\n\n"
            f"{proc.stderr}\n"
            "Run `gh auth login` (or unset a stale GITHUB_TOKEN env var) and retry.\n"
        )
        sys.exit(2)


def _read_pinned_version() -> str:
    """Return the `version` value from `tooling.toml`.

    Exits 2 with an actionable error on any structural issue (file
    missing, invalid TOML, key missing) so the user knows to fix the
    config rather than seeing a Python traceback.
    """
    if not TOOLING_TOML.exists():
        sys.stderr.write(
            f"check-sync-lag: {TOOLING_TOML} not found. Are you running from "
            "the repo root?\n"
        )
        sys.exit(2)
    try:
        with TOOLING_TOML.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        sys.stderr.write(f"check-sync-lag: cannot parse tooling.toml: {e}\n")
        sys.exit(2)
    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        sys.stderr.write(
            "check-sync-lag: `version` key missing or non-string in tooling.toml.\n"
        )
        sys.exit(2)
    return version.strip()


def _fetch_latest_tag(repo: str) -> str:
    """Return the tag_name of the latest release on `repo` (owner/name).

    Wraps `gh api ... --jq .tag_name`. Calls `_gh_preflight()` first.
    """
    _gh_preflight()
    cmd = ["gh", "api", f"repos/{repo}/releases/latest", "--jq", ".tag_name"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as e:
        sys.stderr.write(f"check-sync-lag: cannot invoke `gh`: {e}\n")
        sys.exit(2)
    if proc.returncode != 0:
        sys.stderr.write(
            "check-sync-lag: `gh api releases/latest` failed:\n"
            f"  stdout: {proc.stdout}\n"
            f"  stderr: {proc.stderr}\n"
        )
        sys.exit(2)
    tag = proc.stdout.strip()
    if not tag:
        sys.stderr.write(
            f"check-sync-lag: `gh api` returned empty tag for {repo}/releases/latest.\n"
        )
        sys.exit(2)
    return tag


_DEFAULT_REPO_SLUG = "jsmithpkp21/tooling"
# Accept only `owner/name` shapes with the same character set GitHub
# allows: alnum, `_`, `-`, `.` (with no leading dot). Anchors prevent
# trailing path segments from leaking through.
# Each half MUST start with an alphanumeric so dot-only or
# path-traversal shapes (`..`, `.`, `./..`, `../tooling`) are rejected.
# Subsequent chars allow GitHub's full set: alnum, `_`, `-`, `.`.
_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _repo_slug_from_tooling_toml() -> str:
    """Read `repo` URL from tooling.toml and parse owner/name. Strict:

      - Only `https://github.com/<owner>/<name>(.git)?` is recognized.
      - SSH URLs (`git@github.com:...`), non-github hosts, and shapes
        with extra path segments fall back to the default.

    Returns ``"jsmithpkp21/tooling"`` on any parse failure.
    """
    try:
        with TOOLING_TOML.open("rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return _DEFAULT_REPO_SLUG
    url = data.get("repo")
    if not isinstance(url, str):
        return _DEFAULT_REPO_SLUG
    parsed = urlparse(url)
    # Require https AND host == github.com. No real-world tooling.toml
    # uses plain http; tightening to https-only aligns with the
    # docstring contract (#395). Also rejects SSH URLs (parse with
    # empty scheme + netloc), GitLab-style hosts, and any URL that
    # doesn't structurally resolve to GitHub.
    if parsed.scheme != "https":
        return _DEFAULT_REPO_SLUG
    if parsed.hostname != "github.com":
        return _DEFAULT_REPO_SLUG
    # Path is `/owner/name` or `/owner/name.git`. Strip slashes + `.git`,
    # then validate the slug matches the strict `owner/name` shape.
    slug = parsed.path.strip("/").removesuffix(".git")
    if not _REPO_SLUG_RE.fullmatch(slug):
        return _DEFAULT_REPO_SLUG
    return slug


def compare_versions(pinned: str, latest: str) -> tuple[int, str]:
    """Return `(exit_code, human_message)` comparing pinned to latest.

    Both inputs may have a leading `v`; `packaging.version.Version`
    handles that. Returns ``(0, ...)`` when equal, ``(1, ...)`` when
    pinned < latest, ``(2, ...)`` when either string is unparseable.
    Pinned > latest is treated as ``(0, ...)`` with a "pre-release"
    note (consumer ahead of release, e.g. testing a candidate).
    """
    # `packaging.version.Version` natively accepts a single leading
    # `v` (or `V`) prefix and rejects malformed double-prefix shapes
    # like `vv1.2.3`. The earlier `lstrip("v")` was both unnecessary
    # AND wrong: lstrip treats the argument as a char SET and would
    # strip ALL leading v's, silently normalizing `vv1.2.3` to a
    # valid version. Removing the preprocessing entirely lets Version
    # do the right thing in one place. (#395.)
    try:
        p = Version(pinned)
        l = Version(latest)  # noqa: E741 — `l` is fine here
    except InvalidVersion as e:
        return (2, f"cannot parse version ({e})")

    if p == l:
        return (0, f"up-to-date — pinned {pinned} == latest {latest}")
    if p > l:
        return (0, f"ahead of release — pinned {pinned} > latest {latest}")

    # Behind. Determine semver level for the diff.
    if p.major < l.major:
        level = "major"
    elif p.minor < l.minor:
        level = "minor"
    else:
        level = "patch"
    return (
        1,
        f"behind by {level} version — pinned {pinned}, latest {latest}",
    )


def main() -> int:
    pinned = _read_pinned_version()
    repo = _repo_slug_from_tooling_toml()
    latest = _fetch_latest_tag(repo)
    code, message = compare_versions(pinned, latest)
    if code == 0:
        sys.stdout.write(f"check-sync-lag: {message}\n")
    else:
        sys.stderr.write(f"check-sync-lag: {message}\n")
        if code == 1:
            sys.stderr.write(
                f"Bump `version` in tooling.toml to `{latest}` and run "
                "`make sync-tooling`.\n"
                f"Release notes: https://github.com/{repo}/releases/tag/{latest}\n"
            )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
