"""The brief's six questions against the real, configured LLM: an evaluation, not a unit test.

    pytest -m live          # needs Postgres and LLM_API_KEY; makes ~15 LLM calls

The unit tests script the model, so they can't show that a real model routes and declines
correctly. These do. Expected figures come from the service layer, not hard-coded, so the checks
follow the data. They're deselected by default (see pyproject.toml): they cost API calls, and a
model can phrase an answer in ways a check doesn't anticipate. Read a failure before trusting it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg
import pytest
from fastapi.testclient import TestClient

from tracker import service
from tracker.config import get_settings
from tracker.grounding import normalized, numbers_in
from tracker.tools import pct, usd

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not get_settings().llm_api_key, reason="LLM_API_KEY is not set"),
]


def bare(formatted: str | None) -> str:
    """ "$130.50B" -> "130.5", "71.1%" -> "71.1": the value as grounding.numbers_in() reads it."""
    assert formatted is not None
    return normalized(formatted.strip("$%xBMT"))


def nvda_revenue_and_net_income(conn: psycopg.Connection) -> set[str]:
    years = service.fundamentals(conn, "NVDA", 3).fiscal_years
    return {bare(usd(y.revenue)) for y in years} | {bare(usd(y.net_income)) for y in years}


def top_gross_margin(conn: psycopg.Connection) -> set[str]:
    return {bare(pct(service.ranking(conn, "gross_margin")[0].value))}


def aapl_pe(conn: psycopg.Connection) -> set[str]:
    pe = service.valuation(conn, "AAPL").trailing_pe
    assert pe is not None
    return {normalized(f"{pe:.1f}")}


def msft_revenue_growth(conn: psycopg.Connection) -> set[str]:
    return {bare(pct(service.fundamentals(conn, "MSFT", 1).fiscal_years[0].revenue_yoy))}


@dataclass
class Case:
    question: str
    route: str
    tools: set[str]  # each must be called at least once
    figures: Callable[[psycopg.Connection], set[str]] | None = None  # must all appear in the answer
    mentions: list[str] = field(default_factory=list)  # some phrase from each group must appear
    fully_grounded: bool = True  # every figure in the answer must be found in a tool result


CASES = [
    Case(
        "What were NVDA's revenue and net income for the last three fiscal years?",
        "numbers",
        {"get_fundamentals"},
        nvda_revenue_and_net_income,
    ),
    Case(
        "Which of the five companies had the highest gross margin last year?",
        "numbers",
        {"compare_companies"},
        top_gross_margin,
        mentions=["NVDA|NVIDIA"],
    ),
    Case("What is AAPL's trailing P/E right now?", "numbers", {"get_valuation"}, aapl_pe),
    Case(
        "What new risk factors did NVDA add in its latest 10-K versus the prior year?",
        "filings",
        {"risk_factor_changes"},
        # NVDA has more new paragraphs than one call returns; the answer must not claim it's complete.
        mentions=["of 31|largest|most significant|selection|some of|not exhaustive|partial|offset|all 31"],
        fully_grounded=False,  # quotes figures from 10-K prose, which the check can't always match
    ),
    Case(
        "How did MSFT's revenue grow last year, and what did management attribute it to?",
        "both",
        {"get_fundamentals", "search_filings"},
        msft_revenue_growth,
        mentions=["Azure|Cloud"],
        fully_grounded=False,  # MD&A figures, sometimes restated by the model in other units
    ),
    Case("What is the company's forward guidance for next quarter?", "none", set()),
]


@pytest.mark.parametrize("case", CASES, ids=[c.question[:40] for c in CASES])
def test_the_brief_questions_with_a_real_model(
    client: TestClient, conn: psycopg.Connection, case: Case
) -> None:
    response = client.post("/ask", json={"question": case.question})
    assert response.status_code == 200, response.text
    answer = response.json()
    text, called = answer["answer"], {c["tool"] for c in answer["tool_calls"]}
    context = f"\n--- answer ---\n{text}\n--- tools: {sorted(called)}"

    assert answer["route"] == case.route, context
    assert case.tools <= called, context
    if case.route == "none":
        assert not answer["tool_calls"], context
    if case.figures:
        missing = case.figures(conn) - numbers_in(text)
        assert not missing, f"expected figures not in the answer: {missing}{context}"
    for group in case.mentions:
        assert any(phrase.lower() in text.lower() for phrase in group.split("|")), f"none of {group}{context}"
    if case.fully_grounded:
        assert answer["unverified_numbers"] == [], context
