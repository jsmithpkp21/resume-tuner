#!/usr/bin/env python3
"""Per-ATS credential store for the application-submission flow.

Reads and writes a gitignored TOML file (default
``data/applications/credentials.toml``) so the user can:

- Re-login to an existing ATS tenant when re-submitting or uploading manually.
- Reuse the same account across postings on the same Workday tenant.
- Record fresh credentials the first time a new ATS is encountered.

This module is read/write only — it never autofills login forms. The
``record_session.py`` / ``fill_session.py`` integration scheduled under
issue #319 is expected to call :func:`lookup` and display the saved
password to the user, who then types it. Display-only avoids accidentally
typing the password into a phishing imitation form (the threat model that
motivated the issue).

Security posture: the credentials file lives in ``data/applications/``,
which is gitignored except for the committed ``credentials.toml.example``
template. The real ``credentials.toml`` is written with mode 0600. There
is no encryption at rest; filesystem permissions and gitignore are the
only barriers. This matches the project's existing
``data/profile/profile.toml`` posture (see #333).

The repo's runtime blocked-input guard
(:func:`resume_builder._runtime_guard.assert_not_blocked_runtime_input`)
is applied to the ``path`` argument so this module cannot be redirected
to read or write inside ``sandbox/`` or ``data/samples/``.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import tomllib
from datetime import date
from pathlib import Path
from typing import Any, cast

import tomli_w

from ._runtime_guard import assert_not_blocked_runtime_input

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "data" / "applications" / "credentials.toml"
_KEY_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize_key(value: str) -> str:
    """Normalize an ATS or tenant identifier to a stable slug.

    Args:
        value: Free-form identifier (e.g. ``"Workday"``, ``"BECU"``).

    Returns:
        Lowercased slug with non-alphanumeric runs collapsed to a single
        underscore.

    Raises:
        ValueError: If the normalized result is empty (TOML keys cannot
            be empty).
    """
    slug = _KEY_NORMALIZE_RE.sub("_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError(f"Cannot normalize empty key: {value!r}")
    return slug


def _load(path: Path) -> dict[str, Any]:
    """Load the credentials TOML, returning ``{}`` if missing.

    The caller is responsible for guarding ``path`` against blocked
    runtime roots; this private helper does not re-check.
    """
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def lookup(
    ats: str,
    tenant: str,
    *,
    path: Path = DEFAULT_CREDENTIALS_PATH,
) -> dict[str, Any] | None:
    """Look up saved credentials for an ``(ats, tenant)`` pair.

    Args:
        ats: ATS family (e.g. ``"workday"``, ``"workable"``,
            ``"greenhouse"``). Normalized to a slug.
        tenant: Tenant slug within the ATS (e.g. ``"becu"``,
            ``"westernunion"``). Normalized to a slug.
        path: Path to the credentials TOML. Defaults to
            ``data/applications/credentials.toml`` under the repo root.

    Returns:
        Dict with the saved entry fields (``username``, ``password``,
        and any optional fields) when a credential is found, or ``None``
        when missing.

    Raises:
        ValueError: If ``path`` resolves into a blocked runtime root
            (``sandbox/`` or ``data/samples/``), or if ``ats`` / ``tenant``
            normalize to empty strings.
    """
    assert_not_blocked_runtime_input(path)
    ats_key = _normalize_key(ats)
    tenant_key = _normalize_key(tenant)
    data = _load(path)
    ats_section = data.get("ats")
    if not isinstance(ats_section, dict):
        return None
    family = ats_section.get(ats_key)
    if not isinstance(family, dict):
        return None
    entry = family.get(tenant_key)
    if not isinstance(entry, dict):
        return None
    return cast(dict[str, Any], entry)


def record(
    ats: str,
    tenant: str,
    username: str,
    password: str,
    *,
    tenant_url: str | None = None,
    notes: str | None = None,
    created: date | None = None,
    path: Path = DEFAULT_CREDENTIALS_PATH,
) -> dict[str, Any]:
    """Record or update credentials for an ``(ats, tenant)`` pair.

    Writes the entry under ``[ats.<ats>.<tenant>]`` in the TOML file. The
    parent directory and file are created on demand; the file is written
    atomically and chmod 0600. Existing entries for the same
    ``(ats, tenant)`` are replaced; entries for other tenants are
    preserved.

    Args:
        ats: ATS family identifier (will be normalized to a slug).
        tenant: Tenant identifier within the ATS (will be normalized).
        username: Account username (typically the user's email).
        password: Account password. Stored as plain text; the security
            barrier is filesystem permissions plus gitignore.
        tenant_url: Optional canonical tenant URL recorded with the entry.
        notes: Optional free-form notes (e.g. "submitted; in-progress").
        created: Optional creation date. Defaults to ``date.today()``.
        path: Path to the credentials TOML file.

    Returns:
        The recorded entry as a dict.

    Raises:
        ValueError: If ``path`` resolves into a blocked runtime root
            (``sandbox/`` or ``data/samples/``); if ``ats`` or ``tenant``
            normalize to empty strings; or if an existing section in the
            file has a non-table shape that would be silently overwritten.
    """
    assert_not_blocked_runtime_input(path)
    ats_key = _normalize_key(ats)
    tenant_key = _normalize_key(tenant)
    entry: dict[str, Any] = {
        "username": username,
        "password": password,
        "created": created or date.today(),
    }
    if tenant_url is not None:
        entry["tenant_url"] = tenant_url
    if notes is not None:
        entry["notes"] = notes

    data = _load(path)
    ats_section = data.setdefault("ats", {})
    if not isinstance(ats_section, dict):
        raise ValueError(f"Existing 'ats' section in {path} is not a table")
    family_section = ats_section.setdefault(ats_key, {})
    if not isinstance(family_section, dict):
        raise ValueError(f"Existing 'ats.{ats_key}' section in {path} is not a table")
    family_section[tenant_key] = entry

    _write_atomic(path, data)
    logger.info(
        "Recorded credential for ats=%s tenant=%s at %s",
        ats_key,
        tenant_key,
        path,
    )
    return entry


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    """Serialize ``data`` and write it to ``path`` atomically (mode 0600)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = tomli_w.dumps(data)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=".credentials.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
