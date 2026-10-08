"""Metric math on hand-made rows."""

from datetime import date

import pytest

from tracker.metrics import Metric, annual_table, rank, trailing_pe
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


def test_trailing_pe() -> None:
    assert trailing_pe(30.0, 1.5) == pytest.approx(20.0)
    assert trailing_pe(30.0, -1.0) is None  # not meaningful for a loss
    assert trailing_pe(30.0, None) is None
