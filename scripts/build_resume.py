"""Compatibility wrapper for ``resume_builder.build_resume`` — see issue #41.

Prefer importing from ``resume_builder.build_resume`` directly. This wrapper keeps
``from scripts.build_resume import X`` (including underscore-prefixed back-compat
aliases) working and preserves the ``python scripts/build_resume.py`` CLI entry.
"""

from __future__ import annotations

# CI venvs don't always run `pip install -e .`; bootstrap src/ onto sys.path
# so `import resume_builder.build_resume` resolves whether the package is installed
# or not. Removable once editable-install is part of `make setup`.
import sys as _sys
from pathlib import Path as _Path

_SRC = _Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

import resume_builder.build_resume as _impl  # noqa: E402
from resume_builder.build_resume import *  # noqa: E402, F401, F403
from resume_builder.build_resume import main  # noqa: E402

# `import *` skips underscore-prefixed names; copy the full implementation
# namespace so legacy callers (`from scripts.build_resume import _private`) and
# tests that monkeypatch underscore attributes keep working unchanged.
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(main())
