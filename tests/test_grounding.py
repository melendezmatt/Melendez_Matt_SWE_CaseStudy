"""Checking an answer's numbers against the tool results."""

from tracker.grounding import numbers_in, unverified_numbers

TOOL_RESULT = '{"revenue": "$130.50B", "gross_margin": "71.1%", "trailing_pe": "45.1x", "eps": "$7.46"}'


def test_numbers_copied_from_the_tools_pass_in_any_spelling() -> None:
    answer = "Revenue was **$130.5 billion**, gross margin 71.1%, and the P/E is 45.1x on EPS of $7.46."
    assert unverified_numbers(answer, [TOOL_RESULT]) == []


def test_calculated_or_invented_numbers_are_flagged() -> None:
    answer = "Revenue was $130.50B, up 114.2%, and the P/E is 46x."
    assert unverified_numbers(answer, [TOOL_RESULT]) == ["46", "114.2"]


def test_years_dates_labels_and_small_counts_are_not_figures() -> None:
    answer = (
        "Over the last 3 fiscal years (FY2024 to FY2026, ended 2026-01-25, i.e. January 25, 2026), H20..."
    )
    assert numbers_in(answer, figures_only=True) == set()


def test_thousands_separators_and_trailing_zeros_are_ignored() -> None:
    assert numbers_in("$331,839 million and 17.80%") == {"331839", "17.8"}


def test_no_tool_results_means_every_figure_is_unverified() -> None:
    assert unverified_numbers("The P/E is 45.1x.", []) == ["45.1"]
