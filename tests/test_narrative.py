"""The year-over-year risk factor comparison."""

from tracker.narrative import compare_sections, without_repeats

SUPPLY = (
    "We depend on a limited number of third parties to manufacture, assemble and test our products "
    "and supply chain disruption could hurt us."
)
COMPETE = (
    "We face intense competition in our markets from established companies and new entrants "
    "with significant resources."
)
PARTNER = (
    "We are finalizing an investment and partnership agreement with a major AI lab, "
    "and there is no assurance it closes."
)
CRYPTO = (
    "Demand for our products from cryptocurrency mining has been volatile "
    "and may decline sharply in future periods."
)


def test_new_and_removed_paragraphs_are_found() -> None:
    changes = compare_sections("\n".join([SUPPLY, COMPETE, PARTNER]), "\n".join([SUPPLY, COMPETE, CRYPTO]))
    assert changes == {"new": [PARTNER], "changed": [], "removed": [CRYPTO]}


def test_a_rewritten_paragraph_is_flagged_as_changed() -> None:
    rewritten = (
        SUPPLY + " Recent export controls and tariffs on components have increased this risk materially."
    )
    assert compare_sections(rewritten, SUPPLY)["changed"] == [rewritten]


def test_changed_years_and_numbers_are_not_changes() -> None:
    latest = COMPETE.replace("markets", "markets in fiscal 2026")
    prior = COMPETE.replace("markets", "markets in fiscal 2025")
    assert compare_sections(latest, prior) == {"new": [], "changed": [], "removed": []}


def test_headings_and_short_lines_are_ignored() -> None:
    assert compare_sections("Risks Related to Our Industry", "Risks Related to Our Business")["new"] == []


def test_the_most_novel_paragraphs_come_first() -> None:
    # PARTNER shares nothing with the prior filing; half_new shares a little with SUPPLY.
    half_new = " ".join(SUPPLY.split()[:9]) + " " + CRYPTO  # new, but opens like SUPPLY
    new = compare_sections("\n".join([half_new, PARTNER]), "\n".join([SUPPLY, COMPETE]))["new"]
    assert new == [PARTNER, half_new]


def test_a_passage_repeated_with_new_numbers_is_dropped() -> None:
    prior_year = COMPETE.replace("markets", "markets in fiscal 2025")
    latest_year = COMPETE.replace("markets", "markets in fiscal 2026")
    assert without_repeats([latest_year, PARTNER, prior_year], key=str) == [latest_year, PARTNER]
