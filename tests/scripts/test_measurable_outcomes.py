from __future__ import annotations

from scripts.measurable_outcomes import has_measurable_outcome


def test_has_measurable_outcome_accepts_percent_and_multiplier_patterns() -> None:
    assert has_measurable_outcome("Reduced runtime by 25 percent")
    assert has_measurable_outcome("Improved throughput 2x")


def test_has_measurable_outcome_accepts_gerund_and_digit_patterns() -> None:
    assert has_measurable_outcome(
        "Eliminating manual release tagging across 15 projects through automation"
    )


def test_has_measurable_outcome_accepts_number_word_counts() -> None:
    assert has_measurable_outcome(
        "Reducing duplicate framework spike efforts by forty percent across teams"
    )
    assert has_measurable_outcome(
        "Mentored five engineers with two promoted within two quarters"
    )


def test_has_measurable_outcome_rejects_unquantified_hype() -> None:
    assert not has_measurable_outcome("Improved framework readability and structure")
    assert not has_measurable_outcome("Demonstrated strong collaboration")
