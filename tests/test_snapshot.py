"""Sanity checks on the committed snapshot, so bad source data can't ship unnoticed. No database:
the rows are read from data/snapshot/ and run through the same metric code as the API."""

from collections import defaultdict

import pytest

from tracker import metrics
from tracker.config import get_settings
from tracker.ingest import read_snapshot
from tracker.models import Fact


@pytest.fixture(scope="module")
def fundamentals() -> list[dict]:
    return read_snapshot(get_settings().snapshot_dir)["fundamentals"]


def test_every_revenue_is_positive(fundamentals: list[dict]) -> None:
    bad = [
        (r["ticker"], r["fiscal_year"], r["value"])
        for r in fundamentals
        if r["metric"] == "revenue" and r["value"] <= 0
    ]
    assert bad == []


def test_margins_are_between_minus_and_plus_100_percent(fundamentals: list[dict]) -> None:
    by_ticker: dict[str, list[Fact]] = defaultdict(list)
    for r in fundamentals:
        by_ticker[r["ticker"]].append(Fact(**r))
    bad = [
        (ticker, y.fiscal_year, field, value)
        for ticker, facts in by_ticker.items()
        for y in metrics.annual_table(facts)
        for field in ("gross_margin", "operating_margin")
        if (value := getattr(y, field)) is not None and not -1 <= value <= 1
    ]
    assert bad == []


def test_each_subtotal_has_one_definition_per_company(fundamentals: list[dict]) -> None:
    # Tagged in some years and derived in others would make margins and growth jump on the switch.
    kinds = defaultdict(set)
    for r in fundamentals:
        if r["metric"] in ("gross_profit", "operating_income"):
            kinds[(r["ticker"], r["metric"])].add(r["concept"].startswith("derived: "))
    assert [key for key, k in kinds.items() if len(k) > 1] == []
