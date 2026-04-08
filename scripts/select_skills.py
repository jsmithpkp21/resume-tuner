#!/usr/bin/env python3
"""Deterministic skills packing for Issue #42.

This stage trims trailing (lowest-priority) skills per category to keep the
rendered skills section near a target line budget while preserving grouped
categories and stable ordering.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)
_MEASURE_BACKEND: Any | None | bool = False

# Target line budget from Issue #42
TARGET_LINES_MIN: int = 11
TARGET_LINES_MAX: int = 13
TARGET_LINES_PREFERRED: int = 12
TARGET_CATEGORY_MAX: int = 9
# Minimum skill count to preserve per category (to avoid empty categories)
MIN_SKILLS_PER_CATEGORY: int = 1
_CHAR_WIDTH_LIMIT: int = 92
_ROLE_TOKEN_PATTERN = re.compile(r"[a-z0-9+#/.-]+")
_ROLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_BULLET_COUNT_WEIGHT = 2.0
_RELATED_SKILL_WEIGHT = 1.0
_ROLE_RELEVANCE_WEIGHT = 3.0


def _load_measure_backend() -> Any | None:
    """Load `measure_skills_lines` lazily so pipeline imports do not require Pillow."""
    global _MEASURE_BACKEND
    if _MEASURE_BACKEND is not False:
        return _MEASURE_BACKEND
    try:
        if __package__ in {None, ""}:
            import measure_skills_lines as skills_measure
        else:
            from scripts import measure_skills_lines as skills_measure
        _MEASURE_BACKEND = skills_measure
        return _MEASURE_BACKEND
    except ModuleNotFoundError as exc:
        logger.warning("skills packing fallback estimator enabled: %s", exc)
        _MEASURE_BACKEND = None
        return None


def _wrap_widths(
    token_widths: list[float], line_limit: float, prefix_width: float
) -> list[float]:
    """Wrap token widths into line widths using space-separated token boundaries."""
    if not token_widths:
        return [prefix_width]
    line_widths: list[float] = [prefix_width]
    current = prefix_width
    for width in token_widths:
        proposed = current + width
        if proposed <= line_limit:
            current = proposed
            line_widths[-1] = current
        else:
            current = width
            line_widths.append(current)
    return line_widths


def _estimate_category_lines_fallback(category: str, skills: list[str]) -> list[float]:
    """Fallback line estimator when Pillow/font metrics are unavailable."""
    prefix = len(f"{category}: ")
    body_tokens = " * ".join(skills).split(" ")
    widths = [float(len(token)) for token in body_tokens if token]
    # Add one char for the inter-token space after each token except the first line start.
    token_widths = [
        width if idx == 0 else width + 1.0 for idx, width in enumerate(widths)
    ]
    return _wrap_widths(token_widths, float(_CHAR_WIDTH_LIMIT), float(prefix))


def _estimate_category_lines_with_fonts(
    measure_backend: Any,
    category: str,
    skills: list[str],
    *,
    font_regular: Any,
    font_bold: Any,
) -> list[float]:
    """Point-accurate wrapped line widths using `measure_skills_lines` helpers."""
    separator = measure_backend.SKILLS_SEPARATOR
    text_width_pt = float(measure_backend._TEXT_WIDTH_PT)
    prefix_width = float(measure_backend.measure_pt(f"{category}: ", font_bold, None))
    space_width = float(measure_backend.measure_pt(" ", font_regular, None))
    tokens = separator.join(skills).split(" ")
    token_widths: list[float] = []
    for idx, token in enumerate(tokens):
        if not token:
            continue
        width = float(measure_backend.measure_pt(token, font_regular, None))
        token_widths.append(width if idx == 0 else width + space_width)
    return _wrap_widths(token_widths, text_width_pt, prefix_width)


def _category_layout_metrics(
    category: str,
    skills: list[str],
    *,
    font_regular: Any | None,
    font_bold: Any | None,
    cache: dict[tuple[str, tuple[str, ...], bool], tuple[int, float]],
) -> tuple[int, float]:
    """Return cached `(line_count, short_tail_penalty)` for one category."""
    use_fonts = font_regular is not None and font_bold is not None
    cache_key = (category, tuple(skills), use_fonts)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    measure_backend = _load_measure_backend()
    if measure_backend is not None and use_fonts:
        widths = _estimate_category_lines_with_fonts(
            measure_backend,
            category,
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )
        line_limit = float(measure_backend._TEXT_WIDTH_PT)
    else:
        widths = _estimate_category_lines_fallback(category, skills)
        line_limit = float(_CHAR_WIDTH_LIMIT)

    short_tail_penalty = 0.0
    if widths:
        utilization = widths[-1] / line_limit
        short_tail_penalty = max(0.0, 0.72 - utilization)

    metrics = (len(widths), short_tail_penalty)
    cache[cache_key] = metrics
    return metrics


def estimate_line_count(
    category: str,
    skills: list[str],
    *,
    font_regular: Any | None,
    font_bold: Any | None,
) -> int:
    """Estimate wrapped line count for one category."""
    if not skills:
        return 0
    measure_backend = _load_measure_backend()
    if (
        measure_backend is not None
        and font_regular is not None
        and font_bold is not None
    ):
        widths = _estimate_category_lines_with_fonts(
            measure_backend,
            category,
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
        )
    else:
        widths = _estimate_category_lines_fallback(category, skills)
    return len(widths)


def _section_layout(
    skills_by_category: dict[str, list[str]],
    *,
    font_regular: Any | None,
    font_bold: Any | None,
    cache: dict[tuple[str, tuple[str, ...], bool], tuple[int, float]] | None = None,
) -> tuple[int, float]:
    """Return (total_lines, short_tail_penalty)."""
    resolved_cache: dict[tuple[str, tuple[str, ...], bool], tuple[int, float]]
    resolved_cache = cache if cache is not None else {}
    total_lines = 0
    short_tail_penalty = 0.0

    for category, skills in skills_by_category.items():
        category_lines, category_tail_penalty = _category_layout_metrics(
            category,
            skills,
            font_regular=font_regular,
            font_bold=font_bold,
            cache=resolved_cache,
        )
        total_lines += category_lines
        short_tail_penalty += category_tail_penalty

    return total_lines, short_tail_penalty


def _layout_score(
    total_lines: int,
    short_tail_penalty: float,
    *,
    target_min: int,
    target_max: int,
    target_category_max: int,
    category_count: int,
    singleton_count: int,
    total_skills: int,
) -> float:
    """Lower score is better; prioritize staying in range, then line fullness."""
    preferred = target_min + ((target_max - target_min) // 2)
    over = max(0, total_lines - target_max)
    under = max(0, target_min - total_lines)
    category_over = max(0, category_count - target_category_max)
    distance = abs(total_lines - preferred)
    # When over budget, prioritize structural progress toward fewer lines.
    # Skill-retention reward is re-enabled only once we are no longer over max.
    skill_retention_reward = 0.0 if over > 0 else (total_skills * 0.05)
    return (
        over * 1000.0
        + under * 500.0
        + category_over * 250.0
        + distance * 25.0
        + short_tail_penalty
        + (category_count * 2.5)
        + (singleton_count * 12.0)
        - skill_retention_reward
    )


def _state_stats(skills_by_category: dict[str, list[str]]) -> tuple[int, int, int]:
    """Return (category_count, singleton_count, total_skills) for score tie-breaks."""
    category_count = len(skills_by_category)
    singleton_count = sum(
        1 for skills in skills_by_category.values() if len(skills) == 1
    )
    total_skills = sum(len(skills) for skills in skills_by_category.values())
    return category_count, singleton_count, total_skills


def _tokenize_role_text(text: str) -> set[str]:
    tokens = {
        token
        for token in _ROLE_TOKEN_PATTERN.findall(text.lower())
        if len(token) >= 2 and token not in _ROLE_STOPWORDS
    }
    return tokens


def _extract_role_context(resume: Any) -> tuple[str, set[str]]:
    parts: list[str] = []
    target_role = str(getattr(resume, "target_role", "") or "").strip()
    if target_role:
        parts.append(target_role)

    job_context = getattr(resume, "job_context", None)
    if job_context is not None:
        role_hint = str(getattr(job_context, "role_hint", "") or "").strip()
        if role_hint:
            parts.append(role_hint)
        description_excerpt = str(
            getattr(job_context, "description_excerpt", "") or ""
        ).strip()
        if description_excerpt:
            parts.append(description_excerpt)

    role_text = " ".join(parts).lower()
    role_tokens = _tokenize_role_text(role_text)
    return role_text, role_tokens


def _collect_skill_usage_signals(resume: Any) -> tuple[Counter[str], Counter[str]]:
    bullet_counts: Counter[str] = Counter()
    related_counts: Counter[str] = Counter()

    for experience in getattr(resume, "experiences", ()) or ():
        for skill in getattr(experience, "related_skills", ()) or ():
            related_counts[str(skill)] += 1
        for bullet in getattr(experience, "bullets", ()) or ():
            for skill in getattr(bullet, "skills", ()) or ():
                bullet_counts[str(skill)] += 1

    return bullet_counts, related_counts


def _skill_role_relevance(skill: str, role_text: str, role_tokens: set[str]) -> float:
    if not role_text:
        return 0.0

    normalized_skill = skill.strip().lower()
    if not normalized_skill:
        return 0.0

    skill_tokens = _tokenize_role_text(normalized_skill)
    if not skill_tokens:
        return 0.0

    exact_phrase_bonus = 1.0 if normalized_skill in role_text else 0.0
    overlap_ratio = len(skill_tokens & role_tokens) / len(skill_tokens)
    return exact_phrase_bonus + overlap_ratio


def prioritize_skills_by_importance(resume: Any) -> dict[str, list[str]]:
    """Order skills so higher-value entries stay earlier during tail trimming."""
    role_text, role_tokens = _extract_role_context(resume)
    bullet_counts, related_counts = _collect_skill_usage_signals(resume)
    known_skills = {
        skill
        for category_skills in resume.skills_by_category.values()
        for skill in category_skills
    }

    unknown_signal_skills = sorted(
        (set(bullet_counts) | set(related_counts)) - known_skills
    )
    if unknown_signal_skills:
        logger.warning(
            "skills prioritization ignored unknown skills not present in skills matrix: %s",
            ", ".join(unknown_signal_skills),
        )

    scores: dict[str, float] = {}
    for skill in set(bullet_counts) | set(related_counts):
        role_relevance = _skill_role_relevance(skill, role_text, role_tokens)
        scores[skill] = (
            bullet_counts[skill] * _BULLET_COUNT_WEIGHT
            + related_counts[skill] * _RELATED_SKILL_WEIGHT
            + role_relevance * _ROLE_RELEVANCE_WEIGHT
        )

    prioritized: dict[str, list[str]] = {}
    for category, skills in resume.skills_by_category.items():
        indexed = list(enumerate(skills))
        indexed.sort(
            key=lambda pair: (
                -round(scores.get(pair[1], 0.0), 3),
                -scores.get(pair[1], 0.0),
                len(pair[1]),
                pair[0],
            )
        )
        prioritized[category] = [skill for _, skill in indexed]

    return prioritized


def _removed_skill_char_count(
    before: dict[str, list[str]], after: dict[str, list[str]]
) -> int:
    """Count removed skill-name characters as a tie-breaker under line pressure."""
    before_counter: Counter[str] = Counter()
    after_counter: Counter[str] = Counter()
    for skills in before.values():
        before_counter.update(skills)
    for skills in after.values():
        after_counter.update(skills)

    removed = before_counter - after_counter
    return sum(len(skill) * count for skill, count in removed.items())


def pack_skills_to_budget(
    skills_by_category: dict[str, list[str]],
    *,
    font_regular: Any | None,
    font_bold: Any | None,
    target_min: int = TARGET_LINES_MIN,
    target_max: int = TARGET_LINES_MAX,
    target_category_max: int = TARGET_CATEGORY_MAX,
) -> dict[str, list[str]]:
    """Trim skills to fit target line budget while reducing singleton/category fragmentation."""
    result = {cat: list(skills) for cat, skills in skills_by_category.items()}
    layout_cache: dict[tuple[str, tuple[str, ...], bool], tuple[int, float]] = {}
    iteration = 0
    max_iterations = 200

    while iteration < max_iterations:
        iteration += 1
        total_lines, total_tail = _section_layout(
            result,
            font_regular=font_regular,
            font_bold=font_bold,
            cache=layout_cache,
        )
        category_count, singleton_count, total_skills = _state_stats(result)
        current_score = _layout_score(
            total_lines,
            total_tail,
            target_min=target_min,
            target_max=target_max,
            target_category_max=target_category_max,
            category_count=category_count,
            singleton_count=singleton_count,
            total_skills=total_skills,
        )
        if (
            target_min <= total_lines <= target_max
            and category_count <= target_category_max
        ):
            break

        best_candidate: dict[str, list[str]] | None = None
        best_category = ""
        best_strategy = ""
        best_removed_chars = -1
        force_progress = (
            total_lines > target_max or category_count > target_category_max
        )
        category_only_pressure = (
            category_count > target_category_max and total_lines <= target_max
        )
        best_score = float("inf") if force_progress else current_score
        for category, skills in result.items():
            candidate_variants: list[tuple[dict[str, list[str]], str]] = []
            if not category_only_pressure and len(skills) > MIN_SKILLS_PER_CATEGORY:
                candidate = {cat: list(values) for cat, values in result.items()}
                candidate[category] = candidate[category][:-1]
                candidate_variants.append((candidate, "trim1"))

            # Single-skill drops often do not reduce line count; evaluate a 2-skill trim
            # candidate so we can take a bigger step when that is what actually unwraps.
            if not category_only_pressure and len(skills) >= (
                MIN_SKILLS_PER_CATEGORY + 2
            ):
                candidate = {cat: list(values) for cat, values in result.items()}
                candidate[category] = candidate[category][:-2]
                candidate_variants.append((candidate, "trim2"))

            # Allow removing singleton categories when over budget; this avoids getting
            # stuck with many 1-skill categories that each consume one full line.
            if total_lines > target_max and len(skills) == 1:
                candidate = {
                    cat: list(values)
                    for cat, values in result.items()
                    if cat != category
                }
                candidate_variants.append((candidate, "drop-category"))

            # Prefer reducing category fragmentation by merging small categories into
            # existing ones. This preserves skills while lowering category count.
            if len(skills) <= 3 and len(result) > 1:
                for target_category in result:
                    if target_category == category:
                        continue
                    candidate = {
                        cat: list(values)
                        for cat, values in result.items()
                        if cat != category
                    }
                    merged = list(candidate[target_category])
                    for skill in skills:
                        if skill not in merged:
                            merged.append(skill)
                    candidate[target_category] = merged
                    candidate_variants.append(
                        (candidate, f"merge-into:{target_category}")
                    )

            for candidate, strategy in candidate_variants:
                candidate_lines, candidate_tail = _section_layout(
                    candidate,
                    font_regular=font_regular,
                    font_bold=font_bold,
                    cache=layout_cache,
                )
                cand_category_count, cand_singleton_count, cand_total_skills = (
                    _state_stats(candidate)
                )
                score = _layout_score(
                    candidate_lines,
                    candidate_tail,
                    target_min=target_min,
                    target_max=target_max,
                    target_category_max=target_category_max,
                    category_count=cand_category_count,
                    singleton_count=cand_singleton_count,
                    total_skills=cand_total_skills,
                )
                removed_chars = _removed_skill_char_count(result, candidate)
                # deterministic tie-breaker by category name then strategy
                if score < best_score or (
                    score == best_score
                    and (
                        (force_progress and removed_chars > best_removed_chars)
                        or (
                            removed_chars == best_removed_chars
                            and (
                                (not best_category or category < best_category)
                                or (
                                    category == best_category
                                    and strategy < best_strategy
                                )
                            )
                        )
                    )
                ):
                    best_candidate = candidate
                    best_score = score
                    best_category = category
                    best_strategy = strategy
                    best_removed_chars = removed_chars

        if best_candidate is None:
            break

        result = best_candidate

    result = {cat: skills for cat, skills in result.items() if skills}
    return result


def select_skills(resume: Any) -> Any:
    """Pipeline stage: trim skills to fit the issue #42 target range."""
    font_regular: Any | None = None
    font_bold: Any | None = None
    measure_backend = _load_measure_backend()
    if measure_backend is not None:
        try:
            font_regular, font_bold, _font_name = measure_backend.load_font_pair(
                require_calibri=False
            )
        except FileNotFoundError as exc:
            logger.warning("skills packing fallback estimator enabled: %s", exc)

    prioritized_skills = prioritize_skills_by_importance(resume)

    trimmed_skills = pack_skills_to_budget(
        prioritized_skills,
        font_regular=font_regular,
        font_bold=font_bold,
        target_min=TARGET_LINES_MIN,
        target_max=TARGET_LINES_MAX,
        target_category_max=TARGET_CATEGORY_MAX,
    )

    from dataclasses import replace as dataclass_replace

    return dataclass_replace(resume, skills_by_category=trimmed_skills)
