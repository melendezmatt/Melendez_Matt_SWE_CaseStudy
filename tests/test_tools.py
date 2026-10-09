"""Tool output the model sees, with the service layer stubbed: no database."""

from datetime import date

import pytest

from tracker import service, tools
from tracker.models import Company, FilingRef, RankingRow, RiskFactorChanges, Source, SourceRef


@pytest.fixture
def changes(monkeypatch: pytest.MonkeyPatch) -> None:
    result = RiskFactorChanges(
        ticker="NVDA",
        latest=FilingRef(fiscal_year=2026, accession="a2", url="u2"),
        prior=FilingRef(fiscal_year=2025, accession="a1", url="u1"),
        new=[f"new {i}" for i in range(31)],
        changed=[f"changed {i}" for i in range(3)],
        removed=[],
    )
    monkeypatch.setattr(service, "risk_factor_changes", lambda conn, ticker: result)


@pytest.mark.usefixtures("changes")
def test_a_cut_off_risk_factor_list_says_so_and_gives_totals() -> None:
    out = tools.risk_factor_changes(None, [], "NVDA")  # type: ignore[arg-type]
    assert out["totals"] == {"new": 31, "changed": 3, "removed": 0}
    assert out["truncated"] is True and len(out["new_paragraphs"]) == 20
    assert "Only part" in out["note"]


@pytest.mark.usefixtures("changes")
def test_the_rest_of_the_list_is_one_call_away() -> None:
    out = tools.risk_factor_changes(None, [], "NVDA", offset=20)  # type: ignore[arg-type]
    assert out["new_paragraphs"] == [f"new {i}" for i in range(20, 31)]
    assert out["truncated"] is False and out["note"] == "These are all the changes found."


def test_paging_reaches_every_paragraph_of_every_list(monkeypatch: pytest.MonkeyPatch) -> None:
    # All three lists longer than a page: one offset must page through each without skipping.
    result = RiskFactorChanges(
        ticker="X",
        latest=FilingRef(fiscal_year=2026, accession="a2", url="u2"),
        prior=FilingRef(fiscal_year=2025, accession="a1", url="u1"),
        new=[f"new {i}" for i in range(31)],
        changed=[f"changed {i}" for i in range(25)],
        removed=[f"removed {i}" for i in range(22)],
    )
    monkeypatch.setattr(service, "risk_factor_changes", lambda conn, ticker: result)
    seen: dict[str, list[str]] = {"new_paragraphs": [], "rewritten_paragraphs": [], "removed_paragraphs": []}
    offset, truncated = 0, True
    while truncated:
        out = tools.risk_factor_changes(None, [], "X", offset=offset)  # type: ignore[arg-type]
        for key in seen:
            seen[key] += out[key]
        offset, truncated = offset + tools.PAGE_SIZE, out["truncated"]
    assert seen["new_paragraphs"] == result.new
    assert seen["rewritten_paragraphs"] == result.changed
    assert seen["removed_paragraphs"] == result.removed


def ranking_of(*period_ends: str) -> list[RankingRow]:
    return [
        RankingRow(
            ticker=f"T{i}",
            fiscal_year=int(end[:4]),
            period_end=date.fromisoformat(end),
            value=0.5 - i / 10,
            sources={"revenue": Source(concept="us-gaap:Revenues", accession=f"000000000{i}-26-000001")},
        )
        for i, end in enumerate(period_ends)
    ]


def stub_ranking(monkeypatch: pytest.MonkeyPatch, rows: list[RankingRow]) -> None:
    companies = [
        Company(
            ticker=r.ticker,
            cik=100 + i,
            name=r.ticker,
            first_fiscal_year=None,
            latest_fiscal_year=None,
            filing_fiscal_years=[],
            latest_price_date=None,
        )
        for i, r in enumerate(rows)
    ]
    monkeypatch.setattr(service, "ranking", lambda conn, metric, fiscal_year, calendar_year: rows)
    monkeypatch.setattr(service, "companies", lambda conn: companies)


def test_a_comparison_of_periods_far_apart_tells_the_model_to_say_so(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_ranking(monkeypatch, ranking_of("2025-01-26", "2025-12-31"))
    out = tools.compare_companies(None, [], "revenue", fiscal_year=2025)  # type: ignore[arg-type]
    assert out["period_ends_span_days"] == 339
    assert "not the same period" in out["note"] and "calendar_year" in out["note"]


def test_a_comparison_of_aligned_periods_has_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_ranking(monkeypatch, ranking_of("2025-12-31", "2025-12-28"))
    out = tools.compare_companies(None, [], "revenue")  # type: ignore[arg-type]
    assert "not the same period" not in out["note"]


def test_citations_link_to_the_filing_each_figure_came_from(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_ranking(monkeypatch, ranking_of("2025-12-31"))
    sources: list[SourceRef] = []
    tools.compare_companies(None, sources, "revenue")  # type: ignore[arg-type]
    assert sources == [
        SourceRef(
            label="T0 FY2025 10-K financial data (SEC XBRL)",
            url="https://www.sec.gov/Archives/edgar/data/100/000000000026000001/0000000000-26-000001-index.htm",
            accession="0000000000-26-000001",
        )
    ]


@pytest.mark.usefixtures("changes")
def test_risk_factor_citations_link_to_both_10ks() -> None:
    sources: list[SourceRef] = []
    tools.risk_factor_changes(None, sources, "NVDA")  # type: ignore[arg-type]
    assert [(s.accession, s.url) for s in sources] == [("a2", "u2"), ("a1", "u1")]
