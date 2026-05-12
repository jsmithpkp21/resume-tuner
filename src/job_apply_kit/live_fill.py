"""Pure-function gate + helpers for the Phase 3-B live-fill path (#363).

`fill_application.py`'s `on_snapshot` consumes a Match / Skip decision
from `label_matcher` and — when `--live` is set — turns Matches into
Playwright DOM actions. The gate logic deciding "fill this or just
log it?" lives here so it's testable without Playwright:

  - `decide_fill(...)` is the single gate. Inputs: the matcher's
    answer (`section`, `sub_key`, `skip_reason`) and the CLI's
    `--live` / `--fill-sections` flags. Output: one `FillDecision`
    literal that drives both the DOM action and the log line.
  - `parse_type_delay_range("50-150")` parses the `--type-delay-ms`
    flag into a `(min_ms, max_ms)` pair, validating shape + ordering.
  - `pick_typing_delay(rng, source)` returns a uniformly-jittered
    per-keystroke delay using an injected RNG (so tests can seed).

Hard safety rails encoded here (no override path):

  - honeypots NEVER fill
  - `[account]` matches dispatch to the #341 credential hook (display
    only, never autofill) — `decide_fill` returns "skip-account" to
    flag this
  - `[work_experience]` is skipped until Phase 3-C lands the
    per-role loop
"""

from __future__ import annotations

from typing import Literal, Protocol

# Decisions are returned as string literals (cheap to log, easy to
# match in tests) rather than enums. Each value names both the
# behavior and the reason — log lines + decisions JSON can use it
# verbatim.
FillDecision = Literal[
    "fill",
    "skip-dry-run",
    "skip-honeypot",
    "skip-account",
    "skip-work-experience",
    "skip-section-gated",
    "skip-unfillable",  # Skip reasons from matcher: empty-value, etc.
]


# Sections that are ALWAYS handled specially regardless of the
# `--fill-sections` whitelist. Listed here so the gate is the
# single source of truth.
_HARD_SKIP_SECTIONS = {
    "work_experience": "skip-work-experience",
    "honeypot": "skip-honeypot",
}


def decide_fill(
    *,
    section: str | None,
    sub_key: str | None,
    skip_reason: str | None,
    live: bool,
    allowed_sections: frozenset[str],
) -> FillDecision:
    """Decide what `fill_application` should do with a single field.

    Args:
        section: The matcher's resolved section (e.g. ``"name"``,
            ``"account"``). ``None`` for Skip decisions where no
            section was identified.
        sub_key: The matcher's resolved sub_key. Used only to detect
            the ``account.password_lookup_path`` credential-hook
            handoff; otherwise ignored.
        skip_reason: For Skip decisions, the matcher's ``reason``
            string (``"honeypot"``, ``"empty-value"``,
            ``"unresolved-sub-key"``, ``"intentional-skip"``,
            ``"no-match"``). ``None`` for Match decisions.
        live: True when ``--live`` was passed; False for dry-run.
        allowed_sections: The set of bank sections the user opted in
            to via ``--fill-sections``. Honored only for "normal"
            Match decisions — hard-skip sections (honeypot /
            work_experience) and the account-special-case ignore this.

    Returns:
        A ``FillDecision`` literal:

        - ``"fill"`` — perform a Playwright DOM action.
        - ``"skip-honeypot"`` — matcher flagged a known anti-bot
          pattern; never touch.
        - ``"skip-account"`` — matched the credential-pointer field;
          caller should dispatch to ``credential_hook`` (display
          banner, no autofill — #341 threat model).
        - ``"skip-work-experience"`` — deferred to Phase 3-C
          per-role loop.
        - ``"skip-section-gated"`` — Match landed in a section the
          user didn't opt in to with ``--fill-sections``.
        - ``"skip-dry-run"`` — live mode is off; log only.
        - ``"skip-unfillable"`` — matcher returned a Skip for a
          non-honeypot reason (empty-value, unresolved-sub-key,
          intentional-skip, no-match); nothing to fill.
    """
    # Skip decisions take precedence — honeypot first (hard rail),
    # then everything else falls into the catch-all.
    if skip_reason == "honeypot":
        return "skip-honeypot"
    if skip_reason is not None:
        # empty-value, unresolved-sub-key, intentional-skip, no-match
        # — log only, no fill regardless of live mode.
        return "skip-unfillable"

    # Match: apply hard-skip and credential-hook routing first.
    if section in _HARD_SKIP_SECTIONS:
        # Cast is safe — the map is closed-ended and mypy knows the
        # values are FillDecision literals.
        return _HARD_SKIP_SECTIONS[section]  # type: ignore[return-value]
    if section == "account" and sub_key == "password_lookup_path":
        return "skip-account"

    # Live-mode + section-whitelist gates.
    if not live:
        return "skip-dry-run"
    if section is None or section not in allowed_sections:
        return "skip-section-gated"
    return "fill"


def parse_type_delay_range(spec: str) -> tuple[int, int]:
    """Parse ``--type-delay-ms`` of the form ``"MIN-MAX"`` (e.g.
    ``"50-150"``) into a ``(min, max)`` int pair.

    Both values must be non-negative integers and ``min <= max``.

    Raises:
        ValueError: If the spec is malformed (missing dash, non-int
            sides, negative, or min > max).
    """
    if "-" not in spec:
        raise ValueError(
            f"--type-delay-ms must be 'MIN-MAX' (got {spec!r}); example: '50-150'"
        )
    # `rpartition` so a leading minus on the min value is preserved
    # (`"-10-150"` → `("-10", "-", "150")` rather than `("", "-",
    # "10-150")`). The non-negative check below then catches it with
    # a clearer error message.
    lo_str, _, hi_str = spec.rpartition("-")
    try:
        lo, hi = int(lo_str), int(hi_str)
    except ValueError as e:
        raise ValueError(
            f"--type-delay-ms must be 'MIN-MAX' integers (got {spec!r})"
        ) from e
    if lo < 0 or hi < 0:
        raise ValueError(f"--type-delay-ms values must be non-negative (got {spec!r})")
    if lo > hi:
        raise ValueError(f"--type-delay-ms min must be <= max (got {spec!r})")
    return (lo, hi)


class _RngLike(Protocol):
    """The minimal Random-like surface we need. `random.Random`
    satisfies this; tests inject seeded fakes."""

    def randint(self, a: int, b: int) -> int: ...


def pick_typing_delay(rng: tuple[int, int], source: _RngLike) -> int:
    """Pick a uniformly-jittered per-keystroke delay in milliseconds
    from ``rng`` (inclusive bounds) using ``source.randint``.

    Args:
        rng: ``(min_ms, max_ms)`` pair from ``parse_type_delay_range``.
        source: Any object with a ``randint(a, b)`` method; the live
            caller passes a ``random.Random`` instance, tests pass a
            seeded ``Random()`` for determinism.
    """
    lo, hi = rng
    return source.randint(lo, hi)
