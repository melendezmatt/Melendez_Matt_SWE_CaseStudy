"""Metric math on hand-made rows."""

from datetime import date

import pytest

from tracker.metrics import Metric, annual_table, calendar_year, rank, trailing_pe
from tracker.models import Fact, Source


def rows(period_end: str, **values: float) -> list[Fact]:
    end = date.fromisoformat(period_end)
    return [
        Fact(
            ticker="X",
            metric=m,
            fiscal_year=end.year,
            period_end=end,
            value=v,
            concept=f"us-gaap:{m}",
            accession="a",
        )
        for m, v in values.items()
    ]


TWO_YEARS = rows(
    "2023-12-31", revenue=100, gross_profit=40, operating_income=20, net_income=10, eps_diluted=1.0
) + rows("2024-12-31", revenue=120, gross_profit=54, operating_income=30, net_income=15, eps_diluted=1.5)


def test_margins_and_growth() -> None:
    first, latest = annual_table(TWO_YEARS)
    assert latest.gross_margin == pytest.approx(0.45)
    assert latest.operating_margin == pytest.approx(0.25)
    assert latest.revenue_yoy == pytest.approx(0.20)
    assert latest.net_income_yoy == pytest.approx(0.50)
    assert latest.eps_diluted_yoy == pytest.approx(0.50)
    assert first.revenue_yoy is None  # nothing to compare the first year with
    assert latest.sources["revenue"] == Source(concept="us-gaap:revenue", accession="a")


def test_no_growth_across_a_missing_year() -> None:
    table = annual_table(rows("2021-12-31", revenue=100) + rows("2023-12-31", revenue=150))
    assert table[-1].revenue_yoy is None


def test_no_growth_from_a_loss() -> None:
    table = annual_table(rows("2023-12-31", net_income=-5) + rows("2024-12-31", net_income=5))
    assert table[-1].net_income_yoy is None


def test_missing_values_give_missing_metrics_not_errors() -> None:
    [year] = annual_table(rows("2024-12-31", revenue=100))
    assert year.gross_margin is None and year.operating_income is None


def test_rankings_cite_the_sources_of_their_own_metric() -> None:
    tables = {"X": annual_table(TWO_YEARS)}
    [eps] = rank(tables, Metric.EPS_DILUTED)
    assert set(eps.sources) == {"eps_diluted"}
    [margin] = rank(tables, Metric.GROSS_MARGIN)
    assert set(margin.sources) == {"gross_profit", "revenue"}  # both sides of the ratio


def test_a_company_without_revenue_can_still_be_ranked() -> None:
    # e.g. a bank, which doesn't tag us-gaap:Revenues. This used to raise a KeyError.
    tables = {"X": annual_table(TWO_YEARS), "BANK": annual_table(rows("2024-12-31", net_income=50))}
    ranking = rank(tables, Metric.NET_INCOME)
    assert [r.ticker for r in ranking] == ["BANK", "X"]
    assert set(ranking[0].sources) == {"net_income"}
    assert [r.ticker for r in rank(tables, Metric.GROSS_MARGIN)] == ["X"]  # no margin, so not ranked


def test_a_fiscal_year_belongs_to_the_calendar_year_most_of_it_falls_in() -> None:
    assert calendar_year(date(2026, 1, 25)) == 2025  # NVDA FY2026: Jan 2025 - Jan 2026
    assert calendar_year(date(2026, 6, 30)) == 2025  # MSFT FY2026: Jul 2025 - Jun 2026
    assert calendar_year(date(2025, 9, 27)) == 2025  # AAPL FY2025: Oct 2024 - Sep 2025
    assert calendar_year(date(2025, 12, 31)) == 2025


def test_ranking_by_calendar_year_lines_up_different_year_ends() -> None:
    # A January year-end labelled 2025 ran through 2024; the one labelled 2026 is the 2025 year.
    january = annual_table(rows("2025-01-26", net_income=1) + rows("2026-01-25", net_income=2))
    december = annual_table(rows("2025-12-31", net_income=3))
    tables = {"JAN": january, "DEC": december}
    assert {
        r.ticker: r.period_end.isoformat() for r in rank(tables, Metric.NET_INCOME, fiscal_year=2025)
    } == {
        "JAN": "2025-01-26",
        "DEC": "2025-12-31",
    }
    by_calendar = rank(tables, Metric.NET_INCOME, in_calendar_year=2025)
    assert {r.ticker: r.period_end.isoformat() for r in by_calendar} == {
        "JAN": "2026-01-25",
        "DEC": "2025-12-31",
    }


def test_trailing_pe() -> None:
    assert trailing_pe(30.0, 1.5) == pytest.approx(20.0)
    assert trailing_pe(30.0, -1.0) is None  # not meaningful for a loss
    assert trailing_pe(30.0, None) is None
