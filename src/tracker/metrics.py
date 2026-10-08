"""Metric math: plain functions over rows from the `fundamentals` table. No database, no LLM.

Every number the API or the Q&A agent reports is computed here.
"""

from collections import defaultdict
from datetime import date
from enum import StrEnum

from tracker.models import Fact, FiscalYear, RankingRow, Source

REPORTED = ("revenue", "gross_profit", "operating_income", "net_income", "eps_diluted")
GROWTH = ("revenue", "net_income", "eps_diluted")


class Metric(StrEnum):
    """Metrics that companies can be ranked on: by GET /rankings/{metric} and the agent's
    compare_companies tool. Each value is a FiscalYear field."""

    REVENUE = "revenue"
    NET_INCOME = "net_income"
    EPS_DILUTED = "eps_diluted"
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    REVENUE_YOY = "revenue_yoy"
    NET_INCOME_YOY = "net_income_yoy"
    EPS_DILUTED_YOY = "eps_diluted_yoy"


# The reported values each metric is computed from: what a ranking cites as its source. For growth,
# that's the latest year's value; the prior year's is cited on that year's own row.
INPUTS: dict[Metric, tuple[str, ...]] = {
    Metric.REVENUE: ("revenue",),
    Metric.NET_INCOME: ("net_income",),
    Metric.EPS_DILUTED: ("eps_diluted",),
    Metric.GROSS_MARGIN: ("gross_profit", "revenue"),
    Metric.OPERATING_MARGIN: ("operating_income", "revenue"),
    Metric.REVENUE_YOY: ("revenue",),
    Metric.NET_INCOME_YOY: ("net_income",),
    Metric.EPS_DILUTED_YOY: ("eps_diluted",),
}


def ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator


def growth(current: float | None, prior: float | None) -> float | None:
    # Growth from a loss or zero isn't meaningful (a -$5 to +$5 swing isn't "-200%").
    if current is None or prior is None or prior <= 0:
        return None
    return current / prior - 1


def is_one_year_apart(later: date, earlier: date) -> bool:
    # 52/53-week years run 364-371 days; the window allows for that but rejects a skipped year.
    return 330 <= (later - earlier).days <= 400


def annual_table(facts: list[Fact]) -> list[FiscalYear]:
    """One company's facts as one FiscalYear per period, oldest first: the reported values, gross
    and operating margin, YoY growth, and the XBRL tag and filing behind each reported value."""
    by_period: dict[date, list[Fact]] = defaultdict(list)
    for fact in facts:
        by_period[fact.period_end].append(fact)

    table: list[FiscalYear] = []
    for period_end in sorted(by_period):
        period_facts = by_period[period_end]
        values = {f.metric: f.value for f in period_facts if f.metric in REPORTED}
        prior = table[-1] if table and is_one_year_apart(period_end, table[-1].period_end) else None
        table.append(
            FiscalYear(
                fiscal_year=period_facts[0].fiscal_year,
                period_end=period_end,
                **values,
                gross_margin=ratio(values.get("gross_profit"), values.get("revenue")),
                operating_margin=ratio(values.get("operating_income"), values.get("revenue")),
                **{
                    f"{metric}_yoy": growth(values.get(metric), getattr(prior, metric, None))
                    for metric in GROWTH
                },
                sources={
                    f.metric: Source(concept=f.concept, accession=f.accession)
                    for f in period_facts
                    if f.metric in REPORTED
                },
            )
        )
    return table


def rank(
    tables: dict[str, list[FiscalYear]], metric: Metric, fiscal_year: int | None = None
) -> list[RankingRow]:
    """Every company ranked on one metric, highest first. With no fiscal_year, each company's
    latest year with a value is used. Each row cites the filings behind that metric's inputs."""
    rows = []
    for ticker, table in tables.items():
        years = [
            y
            for y in table
            if getattr(y, metric) is not None and (fiscal_year is None or y.fiscal_year == fiscal_year)
        ]
        if years:
            latest = years[-1]
            rows.append(
                RankingRow(
                    ticker=ticker,
                    fiscal_year=latest.fiscal_year,
                    period_end=latest.period_end,
                    value=getattr(latest, metric),
                    sources={m: latest.sources[m] for m in INPUTS[metric] if m in latest.sources},
                )
            )
    return sorted(rows, key=lambda r: r.value, reverse=True)


def trailing_pe(close: float, eps: float | None) -> float | None:
    """Price / latest annual diluted EPS. Not meaningful when EPS is zero or negative."""
    if eps is None or eps <= 0:
        return None
    return close / eps
