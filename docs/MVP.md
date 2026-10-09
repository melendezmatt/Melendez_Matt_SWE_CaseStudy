# MVP: what the brief requires, and where each requirement is met

This is the minimum feature set that satisfies [the brief](BRIEF.md). Everything in the codebase
traces to a row in the first table. Anything that doesn't is listed under "Deliberately left out"
with the reason.

## Requirements → features

| # | The brief asks for | Feature | Where | Proven by |
|---|---|---|---|---|
| 1 | A fixed universe of 5 tickers, not hardcoded | Tickers in a config file; CIKs looked up from SEC | `config/universe.yaml`, `ingest.fetch()` | `test_companies_show_what_data_is_on_file` |
| 2 | Source 1: SEC XBRL fundamentals | Company facts → one value per company, metric and fiscal year | `sec.py`, `xbrl.py` | `tests/test_xbrl.py`; `test_nvda_revenue_and_net_income_last_three_years` |
| 3 | Source 2: Item 1A and Item 7 text from the latest two 10-Ks | Find the two latest 10-Ks; extract both sections | `filings.py` | `tests/test_filings.py` (incl. ETN's relocated MD&A); all 20 sections in the snapshot |
| 4 | Source 3: market prices | Daily closes from Yahoo Finance (yfinance) | `prices.py` | `test_aapl_trailing_pe_joins_latest_price_and_eps` |
| 5 | A real ingestion pipeline against live sources | `python -m tracker.ingest fetch` | `ingest.py` | Run against SEC + Yahoo to build the committed snapshot |
| 6 | Postgres with a designed schema: fundamentals, filing text, prices | 6 tables; provenance on every number; CHECK constraints; full-text index on filing chunks | `schema.sql` | Loaded by every API test |
| 7 | A seed/snapshot so review doesn't depend on live APIs | Committed snapshot, loaded on first start | `data/snapshot/`, `ingest seed --if-changed` | Every API test loads the snapshot, with no network calls |
| 8 | FastAPI: a few well-structured endpoints for fundamentals, prices, derived metrics | `/companies`, `/fundamentals`, `/prices`, `/valuation`, `/rankings`, `/ask`, `/health`; one error shape | `api/`, `models.py`, `errors.py` | `tests/test_api.py` |
| 9 | Reported: revenue, net income, EPS, gross margin, operating margin | Pivoted from XBRL; untagged subtotals derived and labelled | `xbrl.py`, `metrics.annual_table()` | `test_untagged_subtotals_are_derived_and_labelled`, `test_derived_values_say_how_they_were_derived`, `tests/test_snapshot.py` |
| 10 | Derived: YoY growth and margins | Revenue / net income / EPS growth; gross and operating margin | `metrics.annual_table()` | `tests/test_metrics.py` |
| 11 | One cross-source multiple (EDGAR + market) | Trailing P/E = latest close ÷ latest annual diluted EPS | `service.valuation()`, `metrics.trailing_pe()` | `test_aapl_trailing_pe_joins_latest_price_and_eps` |
| 12 | An NL layer over numbers *and* text, more than chat: tool use / retrieval | Tool-calling agent with 5 tools over the same service layer as the API | `agent.py`, `tools.py` | `tests/test_agent.py`; [EXAMPLES.md](EXAMPLES.md) |
| 13 | **Routing**: numbers, filing text, or both | The model picks tools; the response reports `route` from the tools that actually ran | `agent.route()` | `test_numbers_plus_narrative_question_routes_to_both`; `pytest -m live` checks the route of all six questions against a real model |
| 14 | Decline out-of-scope questions instead of inventing | Coverage and limits in the system prompt; grounding rules | `agent.SYSTEM_PROMPT`; `grounding.py` flags figures not found in any tool result | `pytest -m live` (forward guidance: no tool calls); `tests/test_grounding.py` |
| 15 | LLM base URL, key and model from env vars, never hardcoded | Any OpenAI-compatible endpoint | `config.py`, `.env.example` | `test_ask_without_a_configured_model_is_a_clear_503` |
| 16 | `docker compose up` brings up the whole stack | App + Postgres; seeds itself on first start | `Dockerfile`, `docker-compose.yml` | Manual run (see README) |
| 17 | README: run command, env vars, provider/model, 2–3 example interactions | | `README.md` | |
| 18 | 1–2 page design writeup | Architecture, source integration, where the LLM is and isn't, trade-offs and cuts | `docs/DESIGN.md` | |

### The brief's six example questions

| Question | Type | Tools used | Result |
|---|---|---|---|
| NVDA revenue and net income, last three fiscal years | numbers | `get_fundamentals` | Correct; matches the 10-Ks |
| Highest gross margin last year | numbers, comparative | `compare_companies` | NVDA 71.1%; notes the different fiscal year ends |
| AAPL trailing P/E right now | cross-source join | `get_valuation` | 45.1x = $336.67 ÷ $7.46 |
| New NVDA risk factors vs the prior 10-K | filing text | `risk_factor_changes` | OpenAI agreement, Groq license, China export controls, US manufacturing, data-center energy |
| MSFT revenue growth and management's explanation | numbers + filing text | `get_fundamentals`, `search_filings` | +17.8%, attributed to Microsoft Cloud / Azure +41%, per the FY2026 MD&A |
| Forward guidance next quarter | out of scope | none | Declines; offers what it can provide instead |

Full answers: [EXAMPLES.md](EXAMPLES.md).

## Feature list (what ships)

**Ingestion**
- Live fetch from SEC XBRL company facts, SEC filing history + 10-K documents, and Yahoo Finance
- XBRL clean-up: full-year facts only, latest filing wins (restatements, stock splits), fallback tags per year, zero-tagged values skipped, derived subtotals with the formula recorded (one definition per company across all years)
- A warning at ingestion when a company's own 10-K labels its fiscal year differently from the calendar-year rule
- 10-K section extraction for Item 1A and Item 7, robust to tables of contents, page footers and a relocated MD&A
- Committed, gzipped snapshot (about 370 KB); `seed` loads it with no network access, and
  `seed --if-changed` (run on every start) reloads it whenever the committed snapshot changes

**Storage**
- Postgres schema: `companies`, `fundamentals` (long format with provenance), `prices`, `filings`, `filing_sections`, `filing_chunks` (full-text indexed)

**API**
- `GET /health`: checks the database, not just the process
- `GET /companies` and `GET /companies/{ticker}`: each company with the fiscal years, 10-Ks and latest price on file
- `GET /companies/{ticker}/fundamentals?years=N`: reported values, margins, YoY growth, and the SEC source of each value
- `GET /companies/{ticker}/prices?start=&end=`
- `GET /companies/{ticker}/valuation`: trailing P/E with the price date and the EPS it used
- `GET /rankings/{metric}?fiscal_year=|calendar_year=`: every company ranked on one metric, with the SEC sources of that metric's inputs, so an analyst can check the agent's comparisons; `calendar_year` lines up companies whose fiscal years end in different months
- `POST /ask`: answer, route, tool calls, sources (with EDGAR links and accession numbers in `source_refs`), and any figures not found in a tool result
- One error shape for everything, including unknown routes and crashes: `{"error": {"code", "message", "request_id"}}`, documented in OpenAPI
- Provider rate limits passed through as 429 with `Retry-After`
- A time budget per question (504 when exceeded) and a cap on questions in flight (429), so slow LLM calls can't tie up every worker thread
- `X-Request-ID` on every response, for tracing
- Tickers and metrics validated at the edge (422 before any query runs)

**Q&A agent**
- 5 tools: `get_fundamentals`, `compare_companies`, `get_valuation`, `search_filings`, `risk_factor_changes`
- Numbers pre-formatted for the model; the model does no arithmetic
- Risk factor year-over-year comparison done in code, sorted most novel first, with totals and paging so the model knows when it's seeing part of the list; cached, so paging doesn't recompute it
- Company comparisons report how far apart the fiscal years end, and tell the model to say so past six months
- Filing search defaults to the latest 10-K and drops passages repeated from the prior year
- Every figure in the answer checked against the tool results by kind and value (so a $B/$M slip or a % read as $ is caught, and rounding isn't); any not found are listed in a note at the end of the answer
- Route and sources derived from the tools that ran
- Tool errors (and crashes) returned to the model; a 6-round limit before a forced answer
- A database connection is held only while a tool runs, never while waiting on the model

**Quality**
- 91 tests (unit tests without a database; API tests against the snapshot in Postgres, including `/ask` over HTTP with a fake model)
- A live evaluation, `pytest -m live`: the brief's six questions against the configured real model, checking route, tools, figures and the decline
- Typed end to end: SQL rows map into Pydantic models, and mypy runs clean
- `scripts/check.py`: lint, formatting, types, tests
- `scripts/ask_examples.py`: the brief's six questions against a running server

## Deliberately left out

| Not built | Why | What it would take |
|---|---|---|
| Quarterly (10-Q) data / TTM P/E | The brief allows P/E on the latest annual EPS. TTM doubles ingestion. | 10-Q facts into the same table (it's keyed by period, not year) |
| More multiples (P/S, EV/EBITDA) | The brief asks for one. P/S needs share counts, which are messy for GOOGL's three share classes. | A share-count source; one function in `metrics.py` |
| Historical ("as of") valuation | The brief asks for P/E "right now". | Record when each value was first filed; pick the latest report public on each date |
| Free cash flow, net margin, other line items | Optional or not asked for | A line in `xbrl.METRICS` each |
| Semantic (embedding) search | Keyword search works on 10-K prose, and the reviewer's LLM proxy may not serve embeddings | pgvector + an embedding column on `filing_chunks` |
| Filing search and risk-factor diff as REST endpoints | Available to the agent as tools; the brief asks for endpoints for fundamentals, prices and metrics | A route each over the existing service functions |
| Bonus alternative dataset | Time went to correctness of the three required sources | e.g. SEC Form 4 insider trades through the same pipeline |
| Scheduled refresh, auth, caching, pagination | Prototype scope | Standard additions |
