"""I/O safety helpers shared across the kit's CLI drivers.

Two concerns covered:

1. **Slug sanitization.** CLI `--slug` values are interpolated into output
   filenames (`fields-<slug>-<ts>.json`, `trace-<slug>-<ts>/`). A slug
   containing path separators or `..` can escape the capture dir. The
   `sanitize_slug` helper enforces a `[A-Za-z0-9_-]` allowlist and rejects
   anything else with an explicit error — better than silently slipping
   through to filesystem APIs.

2. **Atomic JSON writes.** The session drivers write JSON incrementally
   (every snapshot / every fill decision) so partial data survives SIGKILL.
   But `Path.write_text(...)` can leave the file truncated if the process
   dies mid-write — a reader hitting the partial file gets JSONDecodeError.
   `atomic_write_json` writes to a temp file in the same directory and
   `os.replace()`s it over the destination, so observers always see either
   the previous full snapshot or the new full snapshot — never partial.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def sanitize_slug(slug: str) -> str:
    """Validate a CLI-supplied slug. Returns it unchanged if safe; raises
    `ValueError` with a clear message otherwise.

    Allowed: alphanumeric + `_` + `-`; must start with alphanumeric (to
    avoid leading `-` being mistaken for a flag by downstream tools).
    Rejects: path separators (`/`, `\\`), parent-dir references (`..`),
    spaces, control characters, anything outside the allowlist.

    Length capped at 80 chars — long enough for `<seq>-<company>-<role>`
    naming conventions, short enough that filenames stay legible.
    """
    if not slug:
        raise ValueError("slug must not be empty")
    if len(slug) > 80:
        raise ValueError(f"slug must be ≤80 chars (got {len(slug)})")
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"slug {slug!r} contains disallowed characters; allowed: "
            "alphanumeric, '_', '-' (must start with alphanumeric)"
        )
    return slug


def atomic_write_json(path: Path, data: Any) -> None:
    """Write `data` to `path` as JSON atomically.

    Strategy: NamedTemporaryFile in the same directory (so `os.replace()`
    is atomic on the same filesystem) → JSON dump → fsync → close → rename.
    Observers reading `path` concurrently see either the old contents or
    the new contents, never a half-written file.

    Indent + UTF-8 by default so the on-disk format is identical to what
    `Path.write_text(json.dumps(data, indent=2))` would produce — drop-in
    replacement.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)
