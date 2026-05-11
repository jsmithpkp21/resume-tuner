"""Compatibility wrapper for ``resume_builder._runtime_guard`` — see issue #41.

Prefer importing from ``resume_builder._runtime_guard`` directly. This wrapper keeps
``from scripts._runtime_guard import X`` working for existing call sites.
"""

from __future__ import annotations

# CI venvs don't always run `pip install -e .`; bootstrap src/ onto sys.path
# so `from resume_builder._runtime_guard import *` resolves whether the package is
# installed or not. Removable once editable-install is part of `make setup`.
import sys as _sys
from pathlib import Path as _Path

_SRC = _Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

from resume_builder._runtime_guard import *  # noqa: E402, F401, F403
