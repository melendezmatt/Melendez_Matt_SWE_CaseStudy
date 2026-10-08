"""Typed models for everything the service layer returns and the API serves.

SQL rows are mapped straight into these with psycopg's `class_row`, so a renamed column or a
missing field fails loudly at the boundary instead of surfacing later as a KeyError or a None.
The API uses the same models as its response schemas, so there's one definition of each shape.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(frozen=True)


# ---- companies and coverage ------------------------------------------------------------------


class Company(Model):
    ticker: str
    cik: int = Field(description="SEC Central Index Key")
    name: str
    first_fiscal_year: int | None
    latest_fiscal_year: int | None
    filing_fiscal_years: list[int] = Field(description="Fiscal years of the 10-Ks whose text is on file")
    latest_price_date: dt.date | None


# ---- fundamentals ----------------------------------------------------------------------------


class Fact(Model):
    """One row of the `fundamentals` table: a reported (or derived) value for one fiscal year."""

    ticker: str
    metric: str
    fiscal_year: int
    period_end: dt.date
    value: float
    concept: str
    accession: str


class Source(Model):
    concept: str = Field(description="XBRL tag the value came from, or 'derived: <formula>'")
    accession: str = Field(description="SEC accession number of the filing")


class FiscalYear(Model):
    """One company's fiscal year: reported values, derived metrics, and where each value came from."""

    fiscal_year: int
    period_end: dt.date
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps_diluted: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    revenue_yoy: float | None = None
    net_income_yoy: float | None = None
    eps_diluted_yoy: float | None = None
    sources: dict[str, Source] = Field(description="Metric name -> the filing and XBRL tag behind it")


class Fundamentals(Model):
    company: Company
    fiscal_years: list[FiscalYear]


# ---- prices and valuation --------------------------------------------------------------------


class Price(Model):
    date: dt.date
    close: float


class Prices(Model):
    ticker: str
    prices: list[Price]


class Valuation(Model):
    ticker: str
    price_date: dt.date
    close: float
    fiscal_year: int
    period_end: dt.date
    eps_diluted: float
    trailing_pe: float | None = Field(description="close / eps_diluted; null when EPS <= 0")
    eps_accession: str


class RankingRow(Model):
    ticker: str
    fiscal_year: int
    period_end: dt.date
    value: float
    sources: dict[str, Source] = Field(description="The reported values the metric is computed from")


# ---- filings ---------------------------------------------------------------------------------


class Passage(Model):
    """A chunk of 10-K text that matched a search."""

    ticker: str
    fiscal_year: int | None
    url: str
    section: str
    text: str
    score: float


class FilingRef(Model):
    fiscal_year: int | None
    url: str


class RiskFactorChanges(Model):
    ticker: str
    latest: FilingRef
    prior: FilingRef
    new: list[str]
    changed: list[str]
    removed: list[str]


# ---- questions -------------------------------------------------------------------------------


class Question(Model):
    question: str = Field(min_length=3, max_length=1000, examples=["What is AAPL's trailing P/E?"])


class ToolCall(Model):
    tool: str
    arguments: str
    ok: bool


Route = Literal["numbers", "filings", "both", "none"]


class Answer(Model):
    answer: str
    route: Route = Field(description="Which data the answer used, from the tools that actually ran")
    tool_calls: list[ToolCall]
    sources: list[str]
    unverified_numbers: list[str] = Field(
        description="Figures in the answer that appear in no tool result: possibly calculated, "
        "converted or invented by the model. Empty when every figure was found."
    )
