"""The API against the committed snapshot, organized around the brief's example questions.

Expected figures are as reported in each company's 10-K, so these also check the ingestion.
The LLM is replaced with a scripted fake through FastAPI's dependency_overrides.
"""

import psycopg
import pytest
from fakes import FakeModel, calls, says
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from tracker import service
from tracker.api.dependencies import get_model
from tracker.errors import LLMRateLimited, LLMUnavailable


def ok(response: Response) -> dict | list:
    assert response.status_code == 200, response.text
    return response.json()


def error_code(response: Response) -> str:
    return response.json()["error"]["code"]


def use_model(app: FastAPI, model: object) -> None:
    app.dependency_overrides[get_model] = lambda: model


def test_health(client: TestClient) -> None:
    assert ok(client.get("/health")) == {"status": "ok"}


def test_companies_show_what_data_is_on_file(client: TestClient) -> None:
    companies = ok(client.get("/companies"))
    assert [c["ticker"] for c in companies] == ["AAPL", "ETN", "GOOGL", "MSFT", "NVDA"]
    nvda = ok(client.get("/companies/nvda"))  # tickers are case-insensitive
    assert nvda["filing_fiscal_years"] == [2025, 2026]
    assert nvda["latest_fiscal_year"] == 2026
    assert nvda == next(c for c in companies if c["ticker"] == "NVDA")


# ---- the brief's questions, answered by the data endpoints ----------------------------------


# "What were NVDA's revenue and net income for the last three fiscal years?"
def test_nvda_revenue_and_net_income_last_three_years(client: TestClient) -> None:
    years = ok(client.get("/companies/NVDA/fundamentals", params={"years": 3}))["fiscal_years"]
    in_millions = [(y["fiscal_year"], y["revenue"] / 1e6, y["net_income"] / 1e6) for y in years]
    assert in_millions == [(2024, 60_922, 29_760), (2025, 130_497, 72_880), (2026, 215_938, 120_067)]
    assert years[-1]["sources"]["revenue"]["concept"] == "us-gaap:Revenues"


# "Which of the five companies had the highest gross margin last year?"
def test_highest_gross_margin_last_year(client: TestClient) -> None:
    ranking = ok(client.get("/rankings/gross_margin"))
    assert [r["ticker"] for r in ranking] == ["NVDA", "MSFT", "GOOGL", "AAPL", "ETN"]
    assert ranking[0]["value"] == pytest.approx(153_463 / 215_938)
    assert {r["period_end"] for r in ranking} > {"2026-01-25", "2025-09-27"}  # fiscal years differ
    assert set(ranking[0]["sources"]) == {"gross_profit", "revenue"}  # both sides of the ratio


def test_ranking_for_one_fiscal_year(client: TestClient) -> None:
    ranking = ok(client.get("/rankings/revenue", params={"fiscal_year": 2025}))
    assert {r["fiscal_year"] for r in ranking} == {2025}
    assert ranking[0]["ticker"] == "AAPL"


# "What is AAPL's trailing P/E right now?"
def test_aapl_trailing_pe_joins_latest_price_and_eps(client: TestClient) -> None:
    v = ok(client.get("/companies/AAPL/valuation"))
    latest_close = ok(client.get("/companies/AAPL/prices"))["prices"][-1]
    assert v["fiscal_year"] == 2025 and v["eps_diluted"] == 7.46
    assert v["price_date"] == latest_close["date"]
    assert v["trailing_pe"] == pytest.approx(latest_close["close"] / 7.46)


# "What new risk factors did NVDA add in its latest 10-K versus the prior year?"
def test_nvda_new_risk_factors(conn: psycopg.Connection) -> None:
    changes = service.risk_factor_changes(conn, "NVDA")
    assert (changes.latest.fiscal_year, changes.prior.fiscal_year) == (2026, 2025)
    assert any("OpenAI" in p for p in changes.new)


# "How did MSFT's revenue grow last year, and what did management attribute it to?"
def test_msft_growth_and_the_mdna_passages_behind_it(client: TestClient, conn: psycopg.Connection) -> None:
    latest = ok(client.get("/companies/MSFT/fundamentals", params={"years": 1}))["fiscal_years"][0]
    assert latest["revenue_yoy"] == pytest.approx(331_839 / 281_724 - 1)
    hits = service.search_filings(conn, "revenue increased driven by Azure", ["MSFT"], "mdna", 2026)
    assert hits and "Azure" in hits[0].text


def test_search_keeps_short_terms_and_defaults_to_the_latest_10k(conn: psycopg.Connection) -> None:
    hits = service.search_filings(conn, "AI", ["NVDA"])  # "AI" used to be dropped as too short
    assert hits and {h.fiscal_year for h in hits} == {2026}


def test_searching_both_years_skips_passages_repeated_from_the_prior_10k(conn: psycopg.Connection) -> None:
    # This sentence is in both NVDA 10-Ks, in near-identical passages. It should come back once,
    # from the latest 10-K, rather than taking two of the six results.
    sentence = "Additional risks, trends and uncertainties not presently known to us"
    hits = service.search_filings(conn, sentence, ["NVDA"], "risk_factors", all_years=True)
    assert [h.fiscal_year for h in hits if sentence in h.text] == [2026]


def test_derived_values_say_how_they_were_derived(client: TestClient) -> None:
    year = ok(client.get("/companies/ETN/fundamentals", params={"years": 1}))["fiscal_years"][0]
    assert year["sources"]["operating_income"]["concept"].startswith("derived: ")


# ---- /ask over HTTP, with real tools and data and a scripted model --------------------------


def test_ask_runs_real_tools_and_reports_the_route(app: FastAPI, client: TestClient) -> None:
    model = FakeModel(calls("get_valuation", arguments='{"ticker": "AAPL"}'), says("AAPL trades at 45.1x."))
    use_model(app, model)
    answer = ok(client.post("/ask", json={"question": "What is AAPL's trailing P/E?"}))
    assert answer["route"] == "numbers"
    assert answer["tool_calls"] == [{"tool": "get_valuation", "arguments": '{"ticker": "AAPL"}', "ok": True}]
    assert any("Yahoo Finance" in s for s in answer["sources"])
    assert answer["unverified_numbers"] == []  # 45.1x is in the tool result
    tool_result = model.requests[1]["messages"][-1]["content"]
    assert '"eps_diluted": "$7.46' in tool_result  # the real tool ran against the snapshot


def test_ask_without_a_configured_model_is_a_clear_503(app: FastAPI, client: TestClient) -> None:
    def no_model() -> None:
        raise LLMUnavailable("LLM_API_KEY is not set")

    app.dependency_overrides[get_model] = no_model
    response = client.post("/ask", json={"question": "What is AAPL's P/E?"})
    assert response.status_code == 503 and error_code(response) == "LLM_UNAVAILABLE"


def test_provider_rate_limits_pass_through_as_429_with_retry_after(app: FastAPI, client: TestClient) -> None:
    use_model(app, FakeModel(LLMRateLimited("slow down", retry_after="30")))
    response = client.post("/ask", json={"question": "What is AAPL's P/E?"})
    assert response.status_code == 429 and error_code(response) == "LLM_RATE_LIMITED"
    assert response.headers["Retry-After"] == "30"


def test_questions_beyond_the_concurrency_limit_are_refused_at_once(app: FastAPI, client: TestClient) -> None:
    use_model(app, FakeModel(says("unused")))
    slots, taken = app.state.ask_slots, 0
    while slots.acquire(blocking=False):  # occupy every slot, as long-running questions would
        taken += 1
    try:
        response = client.post("/ask", json={"question": "What is AAPL's P/E?"})
    finally:
        for _ in range(taken):
            slots.release()
    assert response.status_code == 429 and error_code(response) == "TOO_MANY_QUESTIONS"
    assert response.headers["Retry-After"]
    assert ok(client.get("/health")) == {"status": "ok"}  # the rest of the API is unaffected


# ---- errors and operations --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "status", "code"),
    [
        ("GET", "/companies/TSLA/fundamentals", 404, "NOT_FOUND"),  # not covered
        ("GET", "/companies/NVDA/fundamentals?years=0", 422, "VALIDATION_ERROR"),
        ("GET", "/companies/NV$DA/valuation", 422, "VALIDATION_ERROR"),  # not a ticker
        ("GET", "/rankings/market_share", 422, "VALIDATION_ERROR"),  # not a metric
        ("POST", "/ask", 422, "VALIDATION_ERROR"),  # no body
        ("GET", "/no-such-route", 404, "NOT_FOUND"),
        ("DELETE", "/companies", 405, "METHOD_NOT_ALLOWED"),
    ],
)
def test_every_error_has_the_same_shape(
    app: FastAPI, client: TestClient, method: str, path: str, status: int, code: str
) -> None:
    use_model(app, FakeModel())  # so /ask's 422 doesn't depend on whether LLM_API_KEY is set
    response = client.request(method, path)
    assert response.status_code == status
    error = response.json()["error"]
    assert error["code"] == code and error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_a_callers_request_id_is_echoed_back(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["X-Request-ID"] == "trace-123"


def test_the_openapi_spec_documents_the_error_shape(client: TestClient) -> None:
    spec = ok(client.get("/openapi.json"))
    responses = spec["paths"]["/companies/{ticker}/valuation"]["get"]["responses"]
    assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert set(spec["paths"]["/ask"]["post"]["responses"]) >= {"200", "422", "429", "503", "504"}
