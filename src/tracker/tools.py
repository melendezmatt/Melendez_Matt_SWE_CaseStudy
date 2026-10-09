"""The tools the LLM can call. Each wraps a function in service.py and formats its output.

Numbers are formatted here ("$130.50B", "71.1%") so the model copies them instead of converting
raw figures itself, which is where LLMs most often get numbers wrong.

Every tool has the same signature, (conn, sources, **arguments from the model), and appends a
citation to `sources` for each filing it returns data from, so citations come from the data.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tracker import service
from tracker.db import DbConnection
from tracker.filings import SECTION_TITLES
from tracker.metrics import Metric
from tracker.models import SourceRef
from tracker.sec import filing_index_url

NUMBERS, FILINGS = "numbers", "filings"


def usd(value: float | None) -> str | None:
    if value is None:
        return None
    for size, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= size:
            return f"${value / size:,.2f}{suffix}"
    return f"${value:,.2f}"


def pct(value: float | None) -> str | None:
    return None if value is None else f"{value * 100:.1f}%"


def per_share(value: float | None) -> str | None:
    return None if value is None else f"${value:.2f}"


# How each annual_table() field is shown to the model.
FIELD_FORMATS: dict[str, Callable[[float | None], str | None]] = {
    "revenue": usd,
    "revenue_yoy": pct,
    "gross_profit": usd,
    "gross_margin": pct,
    "operating_income": usd,
    "operating_margin": pct,
    "net_income": usd,
    "net_income_yoy": pct,
    "eps_diluted": per_share,
    "eps_diluted_yoy": pct,
}


def xbrl_sources(ticker: str, cik: int, fiscal_year: int, accessions: Iterable[str]) -> list[SourceRef]:
    """One citation per filing behind a fiscal year's figures. An older year's figures usually
    come from a later 10-K, which restates them."""
    label = f"{ticker} FY{fiscal_year} 10-K financial data (SEC XBRL)"
    return [
        SourceRef(label=label, url=filing_index_url(cik, accession), accession=accession)
        for accession in sorted(set(accessions))
    ]


def filing_source(ticker: str, fiscal_year: int | None, section: str, accession: str, url: str) -> SourceRef:
    label = f"{ticker} FY{fiscal_year} 10-K, {SECTION_TITLES[section]}"
    return SourceRef(label=label, url=url, accession=accession)


# ---- tools ---------------------------------------------------------------------------------


def get_fundamentals(
    conn: DbConnection, sources: list[SourceRef], tickers: list[str], years: int = 3
) -> dict:
    out = {}
    for ticker in tickers:
        data = service.fundamentals(conn, ticker, years)
        symbol = data.company.ticker
        out[symbol] = [
            {
                "fiscal_year": y.fiscal_year,
                "period_end": str(y.period_end),
                **{field: fmt(getattr(y, field)) for field, fmt in FIELD_FORMATS.items()},
            }
            for y in data.fiscal_years
        ]
        for y in data.fiscal_years:
            accessions = (s.accession for s in y.sources.values())
            sources += xbrl_sources(symbol, data.company.cik, y.fiscal_year, accessions)
    return out


# Fiscal years ending further apart than this aren't the same period, and the answer must say so.
ALIGNED_DAYS = 183


def compare_companies(
    conn: DbConnection,
    sources: list[SourceRef],
    metric: str,
    fiscal_year: int | None = None,
    calendar_year: int | None = None,
) -> dict:
    rows = service.ranking(conn, metric, fiscal_year, calendar_year)
    cik = {c.ticker: c.cik for c in service.companies(conn)}
    for r in rows:
        accessions = (s.accession for s in r.sources.values())
        sources += xbrl_sources(r.ticker, cik[r.ticker], r.fiscal_year, accessions)
    if fiscal_year:
        basis = f"fiscal years labelled {fiscal_year}"
    elif calendar_year:
        basis = f"each company's fiscal year that falls mostly in calendar {calendar_year}"
    else:
        basis = "each company's latest fiscal year"
    ends = [r.period_end for r in rows]
    span = (max(ends) - min(ends)).days if ends else 0
    if span > ALIGNED_DAYS:
        note = (
            f"These fiscal years end up to {span} days apart ({min(ends)} to {max(ends)}), so they "
            "are not the same period. Say so in the answer, with each company's period_end. For a "
            "named year, calendar_year lines the years up better than fiscal_year."
        )
    else:
        note = "fiscal years end on different dates for each company; see period_end"
    return {
        "metric": metric,
        "basis": basis,
        "period_ends_span_days": span,
        "note": note,
        "ranking": [
            {
                "rank": rank,
                "ticker": r.ticker,
                "fiscal_year": r.fiscal_year,
                "period_end": str(r.period_end),
                "value": FIELD_FORMATS[metric](r.value),
            }
            for rank, r in enumerate(rows, start=1)
        ],
    }


def get_valuation(conn: DbConnection, sources: list[SourceRef], ticker: str) -> dict:
    v = service.valuation(conn, ticker)
    sources.append(
        SourceRef(
            label=f"{v.ticker} closing price {v.price_date} (Yahoo Finance)",
            url=f"https://finance.yahoo.com/quote/{v.ticker}/history/",
        )
    )
    sources += xbrl_sources(v.ticker, service.company(conn, v.ticker).cik, v.fiscal_year, [v.eps_accession])
    return {
        "ticker": v.ticker,
        "trailing_pe": None if v.trailing_pe is None else f"{v.trailing_pe:.1f}x",
        "price": f"${v.close:.2f} (close on {v.price_date})",
        "eps_diluted": f"{per_share(v.eps_diluted)} (FY{v.fiscal_year}, year ended {v.period_end})",
        "method": "trailing P/E = latest close / latest annual diluted EPS",
    }


def search_filings(
    conn: DbConnection,
    sources: list[SourceRef],
    query: str,
    tickers: list[str] | None = None,
    section: str | None = None,
    fiscal_year: int | None = None,
    all_years: bool = False,
) -> dict:
    passages = []
    for hit in service.search_filings(conn, query, tickers, section, fiscal_year, all_years):
        source = filing_source(hit.ticker, hit.fiscal_year, hit.section, hit.accession, hit.url)
        sources.append(source)
        passages.append({"source": source.label, "text": hit.text})
    return {"query": query, "passages": passages or "no matching passages"}


# Paragraphs returned per call, per list. Each list is ordered most novel first. One size for all
# three lists, so one `offset` pages through each of them without skipping any.
PAGE_SIZE = 20


def risk_factor_changes(conn: DbConnection, sources: list[SourceRef], ticker: str, offset: int = 0) -> dict:
    if offset < 0:
        raise ValueError("offset must be 0 or more")
    changes = service.risk_factor_changes(conn, ticker)
    latest, prior = changes.latest.fiscal_year, changes.prior.fiscal_year
    sources += [
        filing_source(changes.ticker, filing.fiscal_year, "risk_factors", filing.accession, filing.url)
        for filing in (changes.latest, changes.prior)
    ]
    lists = {"new": changes.new, "changed": changes.changed, "removed": changes.removed}
    pages = {name: paras[offset : offset + PAGE_SIZE] for name, paras in lists.items()}
    truncated = any(offset + PAGE_SIZE < len(paras) for paras in lists.values())
    return {
        "ticker": changes.ticker,
        "comparing": f"FY{latest} 10-K vs FY{prior} 10-K",
        "totals": {name: len(paras) for name, paras in lists.items()},
        "offset": offset,
        "truncated": truncated,
        # Appended to the answer by the agent if the model stops here without saying the list is
        # partial (see agent.ask). Written for the reader, not the model.
        "partial_note": (
            f"This covers the {offset + PAGE_SIZE} most changed of {len(changes.new)} new, "
            f"{len(changes.changed)} rewritten and {len(changes.removed)} removed risk factor "
            f"paragraphs in {changes.ticker}'s latest 10-K; ask for more to see the rest."
            if truncated
            else None
        ),
        "note": (
            "Each list is ordered most changed first. Only part of each list is shown; say so in "
            "the answer, or call again with a higher offset for more."
            if truncated
            else "These are all the changes found."
        ),
        "new_paragraphs": pages["new"],
        "rewritten_paragraphs": pages["changed"],
        "removed_paragraphs": pages["removed"],
    }


# ---- registry: what the model is told about each tool ---------------------------------------


@dataclass(frozen=True)
class Tool:
    run: Callable[..., dict]
    category: str  # NUMBERS or FILINGS: how the agent reports its route
    description: str
    parameters: dict
    required: tuple[str, ...]

    @property
    def schema(self) -> dict:
        """The OpenAI-style function definition sent to the model.

        Optional parameters also accept null. Models often send `"fiscal_year": null` to mean "not
        given", and providers that validate arguments against the schema before returning the call
        (Groq does) reject the whole call unless the schema allows it."""
        properties = {
            name: spec if name in self.required else {**spec, "type": [spec["type"], "null"]}
            for name, spec in self.parameters.items()
        }
        return {
            "type": "function",
            "function": {
                "name": self.run.__name__,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(self.required),
                },
            },
        }


TICKER = {"type": "string", "description": 'e.g. "NVDA"'}
TICKERS = {"type": "array", "items": {"type": "string"}, "description": 'e.g. ["NVDA"]'}

TOOLS = {
    tool.run.__name__: tool
    for tool in [
        Tool(
            get_fundamentals,
            NUMBERS,
            "Annual reported financials from 10-K filings: revenue, gross profit, operating income, "
            "net income, diluted EPS, margins and year-over-year growth.",
            {
                "tickers": TICKERS,
                "years": {"type": "integer", "description": "Recent fiscal years (default 3)"},
            },
            ("tickers",),
        ),
        Tool(
            compare_companies,
            NUMBERS,
            "Rank every covered company on one metric. Use for 'which company had the highest ...'. "
            "Omit both years for each company's latest fiscal year ('last year'). For a named year, "
            "prefer calendar_year: fiscal-year labels can be almost a year apart across companies.",
            {
                "metric": {"type": "string", "enum": list(Metric)},
                "fiscal_year": {"type": "integer", "description": "Compare fiscal years with this label"},
                "calendar_year": {
                    "type": "integer",
                    "description": "Compare each company's fiscal year that falls mostly in this year",
                },
            },
            ("metric",),
        ),
        Tool(
            get_valuation,
            NUMBERS,
            "Trailing P/E: the latest closing price divided by the latest annual diluted EPS.",
            {"ticker": TICKER},
            ("ticker",),
        ),
        Tool(
            search_filings,
            FILINGS,
            "Keyword search over the text of 10-K Risk Factors and MD&A. Use for what management "
            "said: explanations, drivers, strategy and risks. Use specific keywords. Searches each "
            "company's latest 10-K unless fiscal_year or all_years says otherwise.",
            {
                "query": {"type": "string"},
                "tickers": TICKERS,
                "section": {"type": "string", "enum": list(SECTION_TITLES)},
                "fiscal_year": {"type": "integer", "description": "Omit for the latest 10-K"},
                "all_years": {
                    "type": "boolean",
                    "description": "Search both 10-Ks on file, e.g. for what changed (default false)",
                },
            },
            ("query",),
        ),
        Tool(
            risk_factor_changes,
            FILINGS,
            "Compare a company's Risk Factors between its two latest 10-Ks and return the paragraphs "
            "that are new, rewritten or removed, most changed first, with the total of each. Use for "
            "'what new risks were added' questions. If `truncated` is true, call again with a higher "
            "offset for more, or say the answer covers only the largest changes.",
            {
                "ticker": TICKER,
                "offset": {
                    "type": "integer",
                    "description": "Skip this many paragraphs per list (default 0)",
                },
            },
            ("ticker",),
        ),
    ]
}
