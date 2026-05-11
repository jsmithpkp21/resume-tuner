"""Compatibility wrapper for ``resume_builder.generate_review_packet`` — see issue #41.

Prefer importing from ``resume_builder.generate_review_packet`` directly. This wrapper keeps
``from scripts.generate_review_packet import X`` working and preserves the
``python scripts/generate_review_packet.py`` CLI entry.
"""

from __future__ import annotations

# CI venvs don't always run `pip install -e .`; bootstrap src/ onto sys.path
# so `from resume_builder.generate_review_packet import *` resolves whether the package is
# installed or not. Removable once editable-install is part of `make setup`.
import sys as _sys
from pathlib import Path as _Path

_SRC = _Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in _sys.path:
    _sys.path.insert(0, str(_SRC))

from resume_builder.generate_review_packet import *  # noqa: E402, F401, F403
from resume_builder.generate_review_packet import (  # noqa: E402 — explicit re-export for CLI dispatch
    main,
)

if __name__ == "__main__":
    raise SystemExit(main())
