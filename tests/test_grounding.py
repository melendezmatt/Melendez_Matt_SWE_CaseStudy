"""Checking an answer's numbers against the tool results."""

import pytest

from tracker.grounding import numbers_in, unverified_numbers

TOOL_RESULT = '{"revenue": "$130.50B", "gross_margin": "71.1%", "trailing_pe": "45.1x", "eps": "$7.46"}'


def test_numbers_copied_from_the_tools_pass_in_any_spelling() -> None:
    answer = (
        "Revenue was **$130.5 billion**, gross margin 71.1 percent, and the P/E is 45.1x on EPS of $7.46."
    )
    assert unverified_numbers(answer, [TOOL_RESULT]) == []


def test_calculated_or_invented_numbers_are_flagged_as_written() -> None:
    answer = "Revenue was $130.50B, up 114.2%, and the P/E is 46x."
    assert unverified_numbers(answer, [TOOL_RESULT]) == ["46x", "114.2%"]


@pytest.mark.parametrize(
    "answer",
    [
        "Revenue was $71.1B.",  # the gross margin's digits, as dollars
        "Gross margin was 130.5%.",  # the revenue's digits, as a percentage
        "Revenue was $130.50 million.",  # the right digits, 1,000 times too small
        "EPS was 7.46 billion.",
        "It trades at 71.1x.",
    ],
)
def test_the_right_digits_with_the_wrong_unit_or_scale_are_flagged(answer: str) -> None:
    assert len(unverified_numbers(answer, [TOOL_RESULT])) == 1


def test_restating_a_figure_in_other_units_or_rounding_it_is_not_flagged() -> None:
    evidence = ['{"revenue": "$331.84B", "revenue_yoy": "17.8%"}']
    answer = "Revenue was $331,839 million ($332B), up 17.8% (18% rounded)."
    assert unverified_numbers(answer, evidence) == []


def test_a_space_before_the_scale_letter_is_the_same_figure() -> None:
    # A Groq model wrote a table of "$60.92 B" cells; every one was flagged until this was fixed.
    assert unverified_numbers("| 2025 | $130.50 B | $7.46 | 71.1 % |", [TOOL_RESULT]) == []


def test_a_bare_number_matches_a_10k_table_in_millions() -> None:
    mdna = "(In millions) Revenue 331,839 281,724"
    assert unverified_numbers("Revenue was $331,839 million.", [mdna]) == []


def test_years_dates_labels_and_small_counts_are_not_figures() -> None:
    answer = (
        "Over the last 3 fiscal years (FY2024 to FY2026, ended 2026-01-25, i.e. January 25, 2026), H20..."
    )
    assert numbers_in(answer, figures_only=True) == set()


def test_thousands_separators_and_trailing_zeros_are_ignored() -> None:
    assert numbers_in("$331,839 million and 17.80%") == {"331839", "17.8"}


def test_no_tool_results_means_every_figure_is_unverified() -> None:
    assert unverified_numbers("The P/E is 45.1x.", []) == ["45.1x"]
