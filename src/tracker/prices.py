"""Daily closing prices from Yahoo Finance, via yfinance."""

from datetime import date

import yfinance as yf


def fetch_daily_closes(ticker: str, start: date) -> list[dict]:
    # With auto_adjust=False, `Close` is adjusted for splits but not dividends. That matches
    # SEC's EPS, which later filings restate after a split, so price / EPS is like-for-like.
    history = yf.Ticker(ticker).history(start=start.isoformat(), auto_adjust=False)
    if history.empty:
        raise ValueError(f"Yahoo Finance returned no prices for {ticker}")
    return [
        {"ticker": ticker, "date": day.date().isoformat(), "close": float(close)}
        for day, close in history["Close"].items()
    ]
