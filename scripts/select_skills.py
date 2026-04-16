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
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)
_MEASURE_BACKEND: Any | None | bool = False

# Target line budget from Issue #42
TARGET_LINES_MIN: int = 11
TARGET_LINES_MAX: int = 13
TARGET_CATEGORY_MAX: int = 9
TOP_N_SKILLS: int = 40
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
_INDUSTRY_SIGNAL_WEIGHT = 4.0
_INDUSTRY_JD_BOOST_WEIGHT = 0.4
SKILLS_SEPARATOR = " • "
_DEFAULT_ANCHOR_SKILLS = frozenset({"Python", "Java"})
_PROTECTED_SKILL_SCORE_FLOOR = 4.0
_PROTECTED_CATEGORY_DROP_PENALTY = 400.0
_PROTECTED_SKILL_DROP_PENALTY = 150.0
_SKILL_ALIAS_CANONICAL: dict[str, str] = {
    "cicd": "ci/cd",
    "ci/cd": "ci/cd",
    "ci-cd": "ci/cd",
    "ci / cd": "ci/cd",
    "continuousintegration/continuousdelivery": "ci/cd",
    "continuousintegrationandcontinuousdelivery": "ci/cd",
}

_INDUSTRY_PROFILE_KEYWORDS: dict[str, frozenset[str]] = {
    "fintech": frozenset(
        {
            "bank",
            "banking",
            "capital",
            "compliance",
            "finance",
            "financial",
            "fintech",
            "fraud",
            "payment",
            "payments",
            "risk",
            "trading",
        }
    ),
    "security": frozenset(
        {
            "cybersecurity",
            "identity",
            "security",
            "soc",
            "threat",
            "vulnerability",
            "zero-trust",
        }
    ),
    "media": frozenset(
        {
            "audio",
            "broadcast",
            "codec",
            "conference",
            "media",
            "streaming",
            "video",
            "voice",
        }
    ),
}

_INDUSTRY_CATEGORY_BASE_WEIGHTS: dict[str, dict[str, float]] = {
    "fintech": {
        "security": 1.2,
        "compliance": 1.0,
        "risk": 0.8,
        "quality": 0.7,
        "automation": 0.7,
        "ci/cd": 0.5,
    },
    "security": {
        "security": 1.2,
        "compliance": 0.8,
        "network": 0.6,
        "reliability": 0.6,
        "automation": 0.5,
    },
    "media": {
        "media": 1.0,
        "video": 0.9,
        "audio": 0.9,
        "network": 0.7,
        "automation": 0.5,
    },
}


def join_skills(skills: Iterable[str]) -> str:
    """Join skills with the shared render/measurement separator."""
    return SKILLS_SEPARATOR.join(skill for skill in skills if skill)


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
    except (ModuleNotFoundError, ImportError) as exc:
        logger.warning("skills packing fallback estimator enabled: %s", exc)
        _MEASURE_BACKEND = None
        return None


def _wrap_widths(
    token_widths: list[float],
    line_limit: float,
    prefix_width: float,
    *,
    inter_token_space: float,
) -> list[float]:
    """Wrap bare token widths and add inter-token spacing only within a line."""
    if not token_widths:
        return [prefix_width]
    line_widths: list[float] = [prefix_width]
    current = prefix_width
    tokens_on_line = 0
    for width in token_widths:
        space = inter_token_space if tokens_on_line > 0 else 0.0
        proposed = current + space + width
        if proposed <= line_limit:
            current = proposed
            line_widths[-1] = current
            tokens_on_line += 1
        else:
            current = width
            line_widths.append(current)
            tokens_on_line = 1
    return line_widths


def _estimate_category_lines_fallback(category: str, skills: list[str]) -> list[float]:
    """Fallback line estimator when Pillow/font metrics are unavailable."""
    prefix = len(f"{category}: ")
    body_tokens = join_skills(skills).split(" ")
    token_widths = [float(len(token)) for token in body_tokens if token]
    return _wrap_widths(
        token_widths,
        float(_CHAR_WIDTH_LIMIT),
        float(prefix),
        inter_token_space=1.0,
    )


def _estimate_category_lines_with_fonts(
    measure_backend: Any,
    category: str,
    skills: list[str],
    *,
    font_regular: Any,
    font_bold: Any,
) -> list[float]:
    """Point-accurate wrapped line widths using `measure_skills_lines` helpers."""
    text_width_pt = float(measure_backend._TEXT_WIDTH_PT)
    prefix_width = float(measure_backend.measure_pt(f"{category}: ", font_bold, None))
    space_width = float(measure_backend.measure_pt(" ", font_regular, None))
    tokens = join_skills(skills).split(" ")
    token_widths: list[float] = []
    for token in tokens:
        if not token:
            continue
        width = float(measure_backend.measure_pt(token, font_regular, None))
        token_widths.append(width)
    return _wrap_widths(
        token_widths,
        text_width_pt,
        prefix_width,
        inter_token_space=space_width,
    )


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


def _compute_skill_scores(resume: Any) -> dict[str, float]:
    """Compute weighted skill importance from usage and role relevance signals.

    All skills present in the skills matrix receive a role-relevance score so
    that the top-N cap (Issue #97) ranks by actual relevance rather than by
    CSV position for skills that appear in no experience bullet or
    related_skills list.
    """
    role_text, role_tokens = _extract_role_context(resume)
    bullet_counts, related_counts = _collect_skill_usage_signals(resume)

    all_matrix_skills: set[str] = {
        skill
        for skills in (getattr(resume, "skills_by_category", None) or {}).values()
        for skill in skills
    }

    scores: dict[str, float] = {}
    for skill in set(bullet_counts) | set(related_counts) | all_matrix_skills:
        role_relevance = _skill_role_relevance(skill, role_text, role_tokens)
        scores[skill] = (
            bullet_counts[skill] * _BULLET_COUNT_WEIGHT
            + related_counts[skill] * _RELATED_SKILL_WEIGHT
            + role_relevance * _ROLE_RELEVANCE_WEIGHT
        )
    return scores


def cap_skills_by_score(
    skills_by_category: dict[str, list[str]],
    scores: dict[str, float],
    top_n: int = TOP_N_SKILLS,
) -> dict[str, list[str]]:
    """Keep only the highest-scoring skills across all categories."""
    if top_n <= 0:
        return {}

    indexed_skills: list[tuple[float, int, str, int]] = []
    global_index = 0
    for category, skills in skills_by_category.items():
        for skill_index, skill in enumerate(skills):
            indexed_skills.append(
                (scores.get(skill, 0.0), global_index, category, skill_index)
            )
            global_index += 1

    if len(indexed_skills) <= top_n:
        return {
            category: list(skills) for category, skills in skills_by_category.items()
        }

    indexed_skills.sort(key=lambda item: (-item[0], item[1]))
    kept_positions = {
        (category, skill_index)
        for _score, _global_index, category, skill_index in indexed_skills[:top_n]
    }

    capped_skills: dict[str, list[str]] = {}
    for category, skills in skills_by_category.items():
        retained = [
            skill
            for skill_index, skill in enumerate(skills)
            if (category, skill_index) in kept_positions
        ]
        if retained:
            capped_skills[category] = retained

    return capped_skills


def _normalize_skill_near_dupe_key(skill: str) -> str:
    """Build a deterministic key for collapsing near-duplicate skill labels."""
    normalized = skill.strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"\s*/\s*", "/", normalized)
    compact = normalized.replace(" ", "")
    return _SKILL_ALIAS_CANONICAL.get(compact, compact)


def normalize_skill_near_dupes(
    skills_by_category: dict[str, list[str]],
    scores: dict[str, float],
) -> dict[str, list[str]]:
    """Collapse near-duplicate skills, keeping the highest-scored variant."""
    winners: dict[str, tuple[str, float, int]] = {}
    global_index = 0
    for _category, skills in skills_by_category.items():
        for skill in skills:
            key = _normalize_skill_near_dupe_key(skill)
            candidate = (skill, scores.get(skill, 0.0), global_index)
            winner = winners.get(key)
            if winner is None or (candidate[1], -len(candidate[0]), -candidate[2]) > (
                winner[1],
                -len(winner[0]),
                -winner[2],
            ):
                winners[key] = candidate
            global_index += 1

    deduped: dict[str, list[str]] = {}
    emitted_keys: set[str] = set()
    for category, skills in skills_by_category.items():
        retained: list[str] = []
        for skill in skills:
            key = _normalize_skill_near_dupe_key(skill)
            winner = winners.get(key)
            if winner is None or key in emitted_keys or winner[0] != skill:
                continue
            retained.append(skill)
            emitted_keys.add(key)
        if retained:
            deduped[category] = retained

    return deduped


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


def _infer_industry_profiles(industry_tokens: set[str]) -> tuple[str, ...]:
    """Infer deterministic industry profiles from role/JD/company tokens."""
    matched: list[str] = []
    for profile, keywords in _INDUSTRY_PROFILE_KEYWORDS.items():
        if industry_tokens & keywords:
            matched.append(profile)
    return tuple(sorted(matched))


def _category_matches_cue(category_tokens: set[str], cue_tokens: set[str]) -> bool:
    if not cue_tokens:
        return False
    return bool(category_tokens & cue_tokens)


def _compute_category_industry_weights(
    resume: Any,
    *,
    skills_by_category: dict[str, list[str]],
) -> dict[str, float]:
    """Compute per-category industry relevance weight (static baseline + JD boost)."""
    _role_text, role_tokens = _extract_role_context(resume)
    industry_tokens: set[str] = set(role_tokens)
    jd_tokens: set[str] = set()

    job_context = getattr(resume, "job_context", None)
    if job_context is not None:
        description_excerpt = str(
            getattr(job_context, "description_excerpt", "") or ""
        ).strip()
        if description_excerpt:
            jd_tokens = _tokenize_role_text(description_excerpt)
        company_research = getattr(job_context, "company_research", None)
        industry_hint = str(
            getattr(company_research, "industry_hint", "") or ""
        ).strip()
        if industry_hint:
            industry_tokens |= _tokenize_role_text(industry_hint)

    profiles = _infer_industry_profiles(industry_tokens)
    if not profiles:
        return {category: 0.0 for category in skills_by_category}

    category_weights: dict[str, float] = {}
    for category in skills_by_category:
        category_tokens = _tokenize_role_text(category)
        weight = 0.0
        for profile in profiles:
            for cue, base_weight in _INDUSTRY_CATEGORY_BASE_WEIGHTS.get(
                profile, {}
            ).items():
                cue_tokens = _tokenize_role_text(cue)
                if not _category_matches_cue(category_tokens, cue_tokens):
                    continue
                weight += base_weight
                if cue_tokens & jd_tokens:
                    weight += _INDUSTRY_JD_BOOST_WEIGHT
        category_weights[category] = weight
    return category_weights


def prioritize_skills_by_importance(
    resume: Any, *, scores: dict[str, float] | None = None
) -> dict[str, list[str]]:
    """Order skills so higher-value entries stay earlier during tail trimming."""
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

    resolved_scores = scores if scores is not None else _compute_skill_scores(resume)

    prioritized: dict[str, list[str]] = {}
    for category, skills in resume.skills_by_category.items():
        indexed = list(enumerate(skills))
        indexed.sort(
            key=lambda pair: (
                -round(resolved_scores.get(pair[1], 0.0), 3),
                -resolved_scores.get(pair[1], 0.0),
                len(pair[1]),
                pair[0],
            )
        )
        prioritized[category] = [skill for _, skill in indexed]

    return prioritized


def _order_categories_by_relevance(
    skills_by_category: dict[str, list[str]],
    *,
    skill_scores: dict[str, float],
    category_industry_weights: dict[str, float] | None = None,
) -> dict[str, list[str]]:
    """Return categories ordered by aggregate retained-skill relevance.

    Category order matters because renderers preserve mapping insertion order for
    both HTML and Markdown output. Use aggregate skill score plus weighted
    category industry signal as the primary key, then industry weight,
    strongest single-skill score, and finally the original category position
    for deterministic ties.
    """
    resolved_category_weights = (
        category_industry_weights if category_industry_weights is not None else {}
    )

    indexed_categories = list(enumerate(skills_by_category.items()))
    indexed_categories.sort(
        key=lambda pair: (
            -(
                sum(skill_scores.get(skill, 0.0) for skill in pair[1][1])
                + (
                    resolved_category_weights.get(pair[1][0], 0.0)
                    * _INDUSTRY_SIGNAL_WEIGHT
                )
            ),
            -resolved_category_weights.get(pair[1][0], 0.0),
            -max((skill_scores.get(skill, 0.0) for skill in pair[1][1]), default=0.0),
            pair[0],
        )
    )
    return {category: skills for _, (category, skills) in indexed_categories}


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


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _protected_drop_penalty(
    before: dict[str, list[str]],
    after: dict[str, list[str]],
    *,
    protected_skills: set[str],
    skill_scores: dict[str, float],
) -> float:
    if not protected_skills:
        return 0.0

    before_counter: Counter[str] = Counter()
    after_counter: Counter[str] = Counter()
    for skills in before.values():
        before_counter.update(skills)
    for skills in after.values():
        after_counter.update(skills)

    removed = before_counter - after_counter
    removed_protected = {
        skill: count for skill, count in removed.items() if skill in protected_skills
    }
    removed_protected_penalty = sum(
        count * (_PROTECTED_SKILL_DROP_PENALTY + (skill_scores.get(skill, 0.0) * 10.0))
        for skill, count in removed_protected.items()
    )

    protected_categories_before = {
        category
        for category, skills in before.items()
        if any(skill in protected_skills for skill in skills)
    }
    protected_categories_after = {
        category
        for category, skills in after.items()
        if any(skill in protected_skills for skill in skills)
    }
    dropped_protected_categories = (
        protected_categories_before - protected_categories_after
    )
    dropped_category_penalty = (
        len(dropped_protected_categories) * _PROTECTED_CATEGORY_DROP_PENALTY
    )
    return removed_protected_penalty + dropped_category_penalty


def pack_skills_to_budget(
    skills_by_category: dict[str, list[str]],
    *,
    font_regular: Any | None,
    font_bold: Any | None,
    target_min: int = TARGET_LINES_MIN,
    target_max: int = TARGET_LINES_MAX,
    target_category_max: int = TARGET_CATEGORY_MAX,
    skill_scores: dict[str, float] | None = None,
    protected_skill_floor: float = _PROTECTED_SKILL_SCORE_FLOOR,
) -> dict[str, list[str]]:
    """Trim skills to fit target line budget while reducing singleton/category fragmentation."""
    result = {cat: list(skills) for cat, skills in skills_by_category.items()}
    known_skills = {skill for skills in result.values() for skill in skills}
    resolved_skill_scores = skill_scores if skill_scores is not None else {}
    protected_skills = {
        skill
        for skill, score in resolved_skill_scores.items()
        if score >= protected_skill_floor and skill in known_skills
    }
    protected_skills |= _DEFAULT_ANCHOR_SKILLS & known_skills
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
            merge_allowed = len(skills) <= 3 or category_only_pressure
            if merge_allowed and len(result) > 1:
                for target_category in result:
                    if target_category == category:
                        continue
                    candidate = {
                        cat: list(values)
                        for cat, values in result.items()
                        if cat != category
                    }
                    source_protected = [
                        skill for skill in skills if skill in protected_skills
                    ]
                    source_other = [
                        skill for skill in skills if skill not in protected_skills
                    ]
                    merged = _dedupe_preserve_order(
                        source_protected
                        + list(candidate[target_category])
                        + source_other
                    )
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
                score += _protected_drop_penalty(
                    result,
                    candidate,
                    protected_skills=protected_skills,
                    skill_scores=resolved_skill_scores,
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
    """Pipeline stage: apply Option A global top-N cap (issue #97) then trim skills to fit the issue #42 target range."""
    from dataclasses import replace as dataclass_replace

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

    skill_scores = _compute_skill_scores(resume)
    capped_resume = dataclass_replace(
        resume,
        skills_by_category=cap_skills_by_score(
            resume.skills_by_category,
            skill_scores,
            top_n=TOP_N_SKILLS,
        ),
    )
    normalized_resume = dataclass_replace(
        capped_resume,
        skills_by_category=normalize_skill_near_dupes(
            capped_resume.skills_by_category,
            skill_scores,
        ),
    )
    prioritized_skills = prioritize_skills_by_importance(
        normalized_resume, scores=skill_scores
    )
    category_industry_weights = _compute_category_industry_weights(
        normalized_resume,
        skills_by_category=prioritized_skills,
    )
    prioritized_skills = _order_categories_by_relevance(
        prioritized_skills,
        skill_scores=skill_scores,
        category_industry_weights=category_industry_weights,
    )

    trimmed_skills = pack_skills_to_budget(
        prioritized_skills,
        font_regular=font_regular,
        font_bold=font_bold,
        target_min=TARGET_LINES_MIN,
        target_max=TARGET_LINES_MAX,
        target_category_max=TARGET_CATEGORY_MAX,
        skill_scores=skill_scores,
    )
    trimmed_skills = _order_categories_by_relevance(
        trimmed_skills,
        skill_scores=skill_scores,
        category_industry_weights=category_industry_weights,
    )

    return dataclass_replace(resume, skills_by_category=trimmed_skills)
