"""Read-side use cases, shared by the REST endpoints and the agent's tools, so the two can never
report different numbers. SQL lives here and returns typed models; math lives in metrics.py."""

import re
from collections import defaultdict
from datetime import date
from typing import Any, TypeVar

from psycopg.rows import class_row
from pydantic import BaseModel

from tracker import metrics, narrative
from tracker.db import DbConnection
from tracker.errors import InvalidInput, NotFound
from tracker.models import (
    Company,
    Fact,
    FilingRef,
    FiscalYear,
    Fundamentals,
    Passage,
    Price,
    Prices,
    RankingRow,
    RiskFactorChanges,
    Valuation,
)

T = TypeVar("T", bound=BaseModel)


def fetch(conn: DbConnection, model: type[T], sql: str, params: Any = None) -> list[T]:
    """Run a query and map each row onto `model` by column name."""
    with conn.cursor(row_factory=class_row(model)) as cur:
        return cur.execute(sql, params).fetchall()


COVERAGE_SQL = """
    SELECT c.ticker, c.cik, c.name,
           (SELECT min(fiscal_year) FROM fundamentals WHERE ticker = c.ticker) AS first_fiscal_year,
           (SELECT max(fiscal_year) FROM fundamentals WHERE ticker = c.ticker) AS latest_fiscal_year,
           (SELECT coalesce(array_agg(fiscal_year ORDER BY fiscal_year), '{}') FROM filings
             WHERE ticker = c.ticker) AS filing_fiscal_years,
           (SELECT max(date) FROM prices WHERE ticker = c.ticker) AS latest_price_date
    FROM companies c
"""


def companies(conn: DbConnection) -> list[Company]:
    """Every covered company and what data exists for it. Also feeds the agent's system prompt."""
    return fetch(conn, Company, COVERAGE_SQL + " ORDER BY c.ticker")


def company(conn: DbConnection, ticker: str) -> Company:
    found = fetch(conn, Company, COVERAGE_SQL + " WHERE c.ticker = %s", (ticker.upper(),))
    if not found:
        raise NotFound(f"{ticker.upper()} is not in the coverage universe")
    return found[0]


def annual_tables(conn: DbConnection, tickers: list[str] | None = None) -> dict[str, list[FiscalYear]]:
    """metrics.annual_table() for each company, from one query. None means every company."""
    facts = fetch(
        conn,
        Fact,
        """
        SELECT ticker, metric, fiscal_year, period_end, value, concept, accession FROM fundamentals
        WHERE %(tickers)s::text[] IS NULL OR ticker = ANY(%(tickers)s)
        ORDER BY ticker, period_end
        """,
        {"tickers": tickers},
    )
    by_ticker: dict[str, list[Fact]] = defaultdict(list)
    for fact in facts:
        by_ticker[fact.ticker].append(fact)
    return {ticker: metrics.annual_table(company_facts) for ticker, company_facts in by_ticker.items()}


def annual_table(conn: DbConnection, ticker: str) -> list[FiscalYear]:
    return annual_tables(conn, [ticker]).get(ticker, [])


def fundamentals(conn: DbConnection, ticker: str, years: int | None = None) -> Fundamentals:
    co = company(conn, ticker)
    table = annual_table(conn, co.ticker)
    return Fundamentals(company=co, fiscal_years=table[-years:] if years else table)


def prices(conn: DbConnection, ticker: str, start: date | None, end: date | None) -> Prices:
    co = company(conn, ticker)
    rows = fetch(
        conn,
        Price,
        """
        SELECT date, close FROM prices
        WHERE ticker = %(ticker)s
          AND (%(start)s::date IS NULL OR date >= %(start)s)
          AND (%(end)s::date IS NULL OR date <= %(end)s)
        ORDER BY date
        """,
        {"ticker": co.ticker, "start": start, "end": end},
    )
    return Prices(ticker=co.ticker, prices=rows)


def valuation(conn: DbConnection, ticker: str) -> Valuation:
    """The cross-source join: latest closing price (Yahoo) / latest annual diluted EPS (SEC)."""
    co = company(conn, ticker)
    latest_prices = fetch(
        conn,
        Price,
        "SELECT date, close FROM prices WHERE ticker = %s ORDER BY date DESC LIMIT 1",
        (co.ticker,),
    )
    with_eps = [(y, y.eps_diluted) for y in annual_table(conn, co.ticker) if y.eps_diluted is not None]
    if not latest_prices or not with_eps:
        raise NotFound(f"not enough data to value {co.ticker}")
    price, (year, eps) = latest_prices[0], with_eps[-1]
    return Valuation(
        ticker=co.ticker,
        price_date=price.date,
        close=price.close,
        fiscal_year=year.fiscal_year,
        period_end=year.period_end,
        eps_diluted=eps,
        trailing_pe=metrics.trailing_pe(price.close, eps),
        eps_accession=year.sources["eps_diluted"].accession,
    )


def ranking(conn: DbConnection, metric: str, fiscal_year: int | None = None) -> list[RankingRow]:
    """Every company ranked on one metric, highest first (see metrics.rank). Fiscal years end on
    different dates, so each row carries period_end."""
    try:
        valid = metrics.Metric(metric)
    except ValueError:
        raise InvalidInput(f"metric must be one of {', '.join(metrics.Metric)}") from None
    return metrics.rank(annual_tables(conn), valid, fiscal_year)


def search_filings(
    conn: DbConnection,
    query: str,
    tickers: list[str] | None = None,
    section: str | None = None,
    fiscal_year: int | None = None,
    all_years: bool = False,
    limit: int = 6,
) -> list[Passage]:
    """Full-text search over the Risk Factors and MD&A chunks, best matches first.

    Searches each company's latest 10-K unless `fiscal_year` names another or `all_years` is set.
    Across years, a passage repeated almost word for word in the older 10-K is dropped, so the
    results aren't spent on the same text twice."""
    # By default Postgres requires *every* word to match. OR them instead, and let the ranking
    # reward passages that match more of them. Short words stay in: "AI", "EU" and "US" matter
    # in 10-Ks, and Postgres drops stopwords itself.
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
    if not words:
        return []
    hits = fetch(
        conn,
        Passage,
        """
        SELECT f.ticker, f.fiscal_year, f.url, c.section, c.text, ts_rank_cd(c.tsv, q) AS score
        FROM filing_chunks c
        JOIN filings f USING (accession),
             to_tsquery('english', %(q)s) q
        WHERE c.tsv @@ q
          AND (%(tickers)s::text[] IS NULL OR f.ticker = ANY(%(tickers)s))
          AND (%(section)s::text IS NULL OR c.section = %(section)s)
          AND (%(fiscal_year)s::int IS NULL OR f.fiscal_year = %(fiscal_year)s)
          AND (%(fiscal_year)s::int IS NOT NULL OR %(all_years)s
               OR f.filed = (SELECT max(filed) FROM filings WHERE ticker = f.ticker))
        ORDER BY score DESC
        LIMIT %(candidates)s
        """,
        {
            "q": " | ".join(words),
            "tickers": [t.upper() for t in tickers] if tickers else None,
            "section": section,
            "fiscal_year": fiscal_year,
            "all_years": all_years,
            "candidates": limit * 3,  # room to drop repeats and still return `limit`
        },
    )
    # Of two near-identical passages, keep the latest 10-K's, then restore best-match-first order.
    newest_first = sorted(hits, key=lambda hit: hit.fiscal_year or 0, reverse=True)
    kept = {id(hit) for hit in narrative.without_repeats(newest_first, key=lambda hit: hit.text)}
    return [hit for hit in hits if id(hit) in kept][:limit]


class RiskFactorText(FilingRef):
    text: str


def risk_factor_changes(conn: DbConnection, ticker: str) -> RiskFactorChanges:
    """What changed in Item 1A between the company's two latest 10-Ks."""
    co = company(conn, ticker)
    filings = fetch(
        conn,
        RiskFactorText,
        """
        SELECT f.fiscal_year, f.url, s.text FROM filings f
        JOIN filing_sections s USING (accession)
        WHERE f.ticker = %s AND s.section = 'risk_factors'
        ORDER BY f.filed DESC LIMIT 2
        """,
        (co.ticker,),
    )
    if len(filings) < 2:
        raise NotFound(f"need two 10-Ks with risk factors for {co.ticker}")
    latest, prior = filings
    return RiskFactorChanges(
        ticker=co.ticker,
        latest=FilingRef(fiscal_year=latest.fiscal_year, url=latest.url),
        prior=FilingRef(fiscal_year=prior.fiscal_year, url=prior.url),
        **narrative.compare_sections(latest.text, prior.text),
    )
