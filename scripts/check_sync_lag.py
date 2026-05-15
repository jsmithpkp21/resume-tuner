#!/usr/bin/env python3
"""Report the gap between a consumer's pinned tooling version and upstream latest.

Promoted to tooling per resume-builder retrospective on PR #389: 4 of
5 Copilot review comments on that sync PR were already fixed in a
newer tooling tag, but the gap wasn't obvious until checked manually.
This target makes "you're N patch versions behind" visible at a glance
from any consumer repo that syncs from this tooling.

Sibling of the four existing quality checks (`check_doc_drift`,
`check_no_type_ignore`, `check_pr_body_drift`, `check_gh_preflight`).
Same shape: pure script, opt-in Makefile target, AGENTS.md-mandated
`gh auth status` preflight before any `gh` call.

Behavior:

  - Reads pinned tooling version from `tooling.toml` `version` key
    (consumer's local copy of tooling.toml; consumers pin a tag like
    `v1.32.1`).
  - Calls `gh api repos/<owner>/<name>/releases/latest --jq .tag_name`
    for the upstream latest tag. `<owner>/<name>` is parsed from the
    `repo` URL in `tooling.toml`; falls back to the consumer's
    upstream if the URL is malformed (rare).
  - Compares via a tiny stdlib `(major, minor, patch)` tuple parser
    so this script has no dependencies beyond the stdlib + `gh` CLI.
    Tooling tags are clean `vMAJOR.MINOR.PATCH`; pre-release suffixes
    are intentionally unsupported (returns exit 2 cannot-parse).
  - Exits:
      0 — pinned == latest (up-to-date) OR pinned > latest (consumer
          ahead of release, e.g. testing a release candidate) OR
          pinned is a branch ref (``main``, ``release/stable``, etc.);
          README documents branch pins as a supported channel and
          comparing to a tag is a category mismatch, not a failure
      1 — pinned < latest (behind; surfaces the gap + level)
      2 — cannot determine (gh missing/unauth, network failure,
          malformed tooling.toml, malformed-tag pinned value such
          as ``v1.2`` or ``v1.2.3-rc1``)
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

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
    missing, symlink, non-regular file, unreadable, invalid TOML, key
    missing) so the user knows to fix the config rather than seeing a
    Python traceback. Mirrors the symlink + is_file + read-error
    guards in `scripts/validate_tooling_toml_drift.py`.
    """
    # Symlink check before exists(): exists() follows symlinks, so a
    # broken symlink would otherwise be reported as missing and bypass
    # the SECURITY guard. Fail closed on any symlink.
    if TOOLING_TOML.is_symlink():
        sys.stderr.write(
            f"check-sync-lag: SECURITY: {TOOLING_TOML} must not be a symbolic link.\n"
        )
        sys.exit(2)
    if not TOOLING_TOML.exists():
        sys.stderr.write(
            f"check-sync-lag: {TOOLING_TOML} not found. Are you running from "
            "the repo root?\n"
        )
        sys.exit(2)
    # Regular-file guard: a FIFO, device, or directory would block or
    # misbehave on read. Matches validate_tooling_toml_drift.py.
    if not TOOLING_TOML.is_file():
        sys.stderr.write(
            f"check-sync-lag: MALFORMED: {TOOLING_TOML} must be a regular file.\n"
        )
        sys.exit(2)
    try:
        with TOOLING_TOML.open("rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        sys.stderr.write(f"check-sync-lag: cannot read tooling.toml: {e}\n")
        sys.exit(2)
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
# Each half MUST start with an alphanumeric so dot-only or
# path-traversal shapes (`..`, `.`, `./..`, `../tooling`) are rejected.
# Subsequent chars allow GitHub's full set: alnum, `_`, `-`, `.`.
_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _repo_slug_from_tooling_toml() -> str:
    """Read `repo` URL from tooling.toml and parse owner/name. Strict:

      - Only ``https://github.com/<owner>/<name>(.git)?`` is recognized.
      - SSH URLs (``git@github.com:...``), non-github hosts, and shapes
        with extra path segments fall back to the default.
      - URLs carrying query strings (``?tab=readme``), fragments
        (``#anchor``), parameters, userinfo, or non-default ports fall
        back to the default — ``urlparse`` puts those in separate
        attributes from ``parsed.path``, so without explicit rejection
        ``https://github.com/acme/tooling?tab=readme`` would otherwise
        slip through as slug ``acme/tooling``.

    Returns the default repo slug on any parse failure.
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
    if parsed.scheme != "https":
        return _DEFAULT_REPO_SLUG
    if parsed.hostname != "github.com":
        return _DEFAULT_REPO_SLUG
    # Reject any URL component that lives outside `parsed.path`, since
    # the slug check only inspects path. github.com release URLs the
    # README documents are bare `https://github.com/<owner>/<name>`
    # with no query / fragment / userinfo / non-default port.
    if parsed.query or parsed.fragment or parsed.params:
        return _DEFAULT_REPO_SLUG
    if parsed.username or parsed.password:
        return _DEFAULT_REPO_SLUG
    # `parsed.port` itself raises ValueError on malformed port text
    # (e.g. `https://github.com:abc/...`). Without the try/except,
    # a bad `repo` value crashes the script with a traceback instead
    # of falling back to the default slug as the function contract
    # promises. (tooling#432.)
    try:
        port = parsed.port
    except ValueError:
        return _DEFAULT_REPO_SLUG
    if port is not None:
        return _DEFAULT_REPO_SLUG
    slug = parsed.path.strip("/").removesuffix(".git")
    if not _REPO_SLUG_RE.fullmatch(slug):
        return _DEFAULT_REPO_SLUG
    return slug


# Strict semver-ish parser for tooling tags. Accepts an optional single
# leading `v` / `V` and requires exactly three numeric components.
# Pre-release / build-metadata suffixes (`-rc1`, `+abc`) are
# intentionally unsupported — tooling tags are clean `vX.Y.Z`.
_VERSION_RE = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)$")


def _parse_version(s: str) -> tuple[int, int, int]:
    """Return `(major, minor, patch)` from a `vX.Y.Z`-shaped tag.

    Raises:
        ValueError: on any non-conforming input. Caller is expected
            to convert to the exit-2 cannot-parse path.
    """
    m = _VERSION_RE.fullmatch(s)
    if m is None:
        raise ValueError(f"not a vMAJOR.MINOR.PATCH tag: {s!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# Branch names that are unambiguously branch refs (not malformed tags).
# Anything with a `/` is also a branch ref because release tags can't
# contain `/`. Everything else falls through to the strict tag parser
# so genuinely malformed input (`not-a-version`, `vv1.2.3`, `v1.2`)
# stays on the exit-2 cannot-parse path with an actionable error
# rather than getting silently treated as a branch pin.
_KNOWN_BRANCH_NAMES = frozenset({"main", "master", "develop", "trunk", "HEAD"})


def _is_branch_ref(s: str) -> bool:
    """True if `s` is a branch ref (`main`, `release/stable`, feature
    branch) rather than a release tag.

    The README documents branch refs as a supported `tooling.toml.version`
    channel; comparing a branch pin against a release tag is a category
    mismatch, not a parse failure. Conservative detection: either a `/`
    is present (impossible in a release tag) or the value matches a
    well-known branch name. Other unrecognized strings stay on the
    cannot-parse path so the operator gets an actionable error.
    """
    if _VERSION_RE.fullmatch(s):
        return False
    if "/" in s:
        return True
    return s in _KNOWN_BRANCH_NAMES


def compare_versions(pinned: str, latest: str) -> tuple[int, str]:
    """Return `(exit_code, human_message)` comparing pinned to latest.

    Both inputs accept a single optional `v` prefix. Returns:

      - ``(0, "up-to-date — ...")`` when pinned == latest
      - ``(0, "ahead of release — ...")`` when pinned > latest
        (consumer testing a release candidate)
      - ``(0, "tracking branch — ...")`` when pinned is a branch ref
        (any value containing ``/`` like ``release/stable`` or
        ``feature/X``, or a well-known branch name like ``main``,
        ``master``, ``develop``). The README documents this as a
        supported channel; comparison to a tag is a category mismatch,
        not a failure. The message still surfaces the latest release
        tag so the operator can decide whether to pin instead.
      - ``(1, "behind by <level> ...")`` when pinned < latest
      - ``(2, "cannot parse ...")`` when either string is malformed
        and not a recognized branch ref (e.g. ``v1.2``, ``v1.2.3-rc1``,
        ``vv1.2.3``, ``not-a-version``).
    """
    # Branch-ref pinned (main / release/stable / feature/X): comparison
    # to a tag is a category mismatch, not a parse failure. Surface
    # the latest tag so the operator can decide whether to pin.
    if _is_branch_ref(pinned):
        return (
            0,
            f"tracking branch — pinned {pinned!r} is a branch ref, "
            f"not a release tag. Latest released tag: {latest}.",
        )

    try:
        p = _parse_version(pinned)
        l = _parse_version(latest)  # noqa: E741 — `l` is fine here
    except ValueError as e:
        return (2, f"cannot parse version ({e})")

    if p == l:
        return (0, f"up-to-date — pinned {pinned} == latest {latest}")
    if p > l:
        return (0, f"ahead of release — pinned {pinned} > latest {latest}")

    # Behind. Determine semver level for the diff.
    if p[0] < l[0]:
        level = "major"
    elif p[1] < l[1]:
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
