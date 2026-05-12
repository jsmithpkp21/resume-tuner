"""job_apply_kit — Workday/ATS-specific helpers for the application-submission arc.

Sibling package to `resume_builder` and `playwright_stealth_kit`. Holds the
non-job-application-specific pieces that operate on a captured-or-live
apply form:

- `label_matcher`: pure-function matcher that takes a form field's label
  + an answer bank (TOML) and returns what to fill (or skip, in the case
  of the honeypot or an unrecognized label). Includes per-section
  sub-field heuristics for [name] / [contact] / [address] / [links] /
  [education] / [account] / [profile_fields].
- `match_replay`: offline tool that replays the matcher against captured
  `fields-*.json` files and reports per-session match-rate stats. Useful
  for validating the matcher against real captures before any live use.
- `field_extractor`: thin wrapper exposing the DOM-walking JS (used by
  the recording / fill drivers via `add_init_script`) as an importable
  Python constant.

The kit's intent is to extract to its own repo (`git filter-repo
--subdirectory-filter src/job_apply_kit`) once a second consumer
materializes outside the resume-builder use case.

See issues #319 (this scaffolding) and #315 (parent application-submission
roadmap).
"""

from .field_extractor import EXTRACTOR_JS, load_extractor_js
from .label_matcher import (
    HONEYPOT_SUBSTRINGS,
    Decision,
    Match,
    Skip,
    is_honeypot,
    match,
    normalize,
)
from .match_replay import replay

__all__ = [
    "Decision",
    "EXTRACTOR_JS",
    "HONEYPOT_SUBSTRINGS",
    "Match",
    "Skip",
    "is_honeypot",
    "load_extractor_js",
    "match",
    "normalize",
    "replay",
]
