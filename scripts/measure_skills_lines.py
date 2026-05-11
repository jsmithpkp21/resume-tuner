"""Compatibility wrapper for ``resume_builder.measure_skills_lines`` — see issue #41.

Prefer importing from ``resume_builder.measure_skills_lines`` directly. This wrapper keeps
``from scripts.measure_skills_lines import X`` (including underscore-prefixed back-compat
aliases) working and preserves the ``python scripts/measure_skills_lines.py`` CLI entry.
"""

from __future__ import annotations

# CI venvs don't always run `pip install -e .`; bootstrap src/ onto sys.path
# so `import resume_builder.measure_skills_lines` resolves whether the package is installed
# or not. Removable once editable-install is part of `make setup`.
import sys as _sys
from pathlib import Path as _Path

_SRC = _Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

import resume_builder.measure_skills_lines as _impl  # noqa: E402
from resume_builder.measure_skills_lines import *  # noqa: E402, F401, F403
from resume_builder.measure_skills_lines import main  # noqa: E402

# `import *` skips underscore-prefixed names; copy the full implementation
# namespace so legacy callers (`from scripts.measure_skills_lines import _private`) and
# tests that monkeypatch underscore attributes keep working unchanged.
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(main())
