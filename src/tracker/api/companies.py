"""/companies: coverage, fundamentals, prices and valuation for one company."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from tracker import service
from tracker.api.dependencies import Connection, Ticker
from tracker.api.errors import error_responses
from tracker.models import Company, Fundamentals, Prices, Valuation

router = APIRouter(prefix="/companies", tags=["companies"], responses=error_responses(404, 422))


@router.get("")
def list_companies(conn: Connection) -> list[Company]:
    """The covered companies, with the fiscal years, 10-Ks and prices on file for each."""
    return service.companies(conn)


@router.get("/{ticker}")
def get_company(conn: Connection, ticker: Ticker) -> Company:
    return service.company(conn, ticker)


@router.get("/{ticker}/fundamentals")
def get_fundamentals(
    conn: Connection,
    ticker: Ticker,
    years: Annotated[int | None, Query(ge=1, le=20, description="Most recent N fiscal years")] = None,
) -> Fundamentals:
    """Reported figures, margins and YoY growth per fiscal year, with the SEC source of each value."""
    return service.fundamentals(conn, ticker, years)


@router.get("/{ticker}/prices")
def get_prices(
    conn: Connection, ticker: Ticker, start: date | None = None, end: date | None = None
) -> Prices:
    """Daily closing prices, oldest first."""
    return service.prices(conn, ticker, start, end)


@router.get("/{ticker}/valuation")
def get_valuation(conn: Connection, ticker: Ticker) -> Valuation:
    """Trailing P/E: the latest close (Yahoo) over the latest annual diluted EPS (SEC)."""
    return service.valuation(conn, ticker)
