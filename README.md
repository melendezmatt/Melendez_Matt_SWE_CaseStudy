# Fundamentals Tracker

A backend service that tracks five companies' fundamentals from SEC filings and market data, and
answers plain-English questions about both the reported numbers and what the 10-Ks say.

- **Data:** SEC XBRL financials, the Risk Factors (Item 1A) and MD&A (Item 7) text of each
  company's latest two 10-Ks, and daily prices from Yahoo Finance
- **Stack:** Python, FastAPI, PostgreSQL, Docker Compose; any OpenAI-compatible LLM with tool calling
- **Companies:** NVDA, MSFT, AAPL, GOOGL, ETN, listed in [`config/universe.yaml`](config/universe.yaml)

The assignment is in [`docs/BRIEF.md`](docs/BRIEF.md). [`docs/MVP.md`](docs/MVP.md) maps every
requirement to the code and the test that proves it. [`docs/DESIGN.md`](docs/DESIGN.md) is the
design writeup.

## My approach

I read the brief as a trust problem. An analyst can't use an answer they can't check, and a wrong
number is worse than "I don't know". So I:

1. **Kept the LLM away from the numbers.** All math is plain Python in `metrics.py`. The model
   chooses which tools to call and writes the answer; it never calculates anything.
2. **Recorded where every number came from.** Each stored value keeps its XBRL tag and the SEC
   filing it came from. Derived values say how they were derived.
3. **Made "what's new in the 10-K" a code problem, not a model problem.** Comparing two risk
   factor sections is done in code, and the model only summarizes the result.
4. **Reported the route from what actually happened.** The `route` and `sources` in each answer
   come from the tools that ran, not from the model's description of itself.
5. **Built the MVP and stopped.** Everything the brief requires, and nothing else. What I left out,
   and why, is in [`docs/MVP.md`](docs/MVP.md#deliberately-left-out).

## Running it

```bash
cp .env.example .env        # add LLM_API_KEY (needed only for /ask)
docker compose up --build
```

On start the app loads the committed snapshot in [`data/snapshot/`](data/snapshot/) into
Postgres, unless the database already holds that exact snapshot. It doesn't need SEC or Yahoo to be
reachable, and a newer committed snapshot is picked up without resetting the database volume. The API is at http://localhost:8000,
with interactive docs at http://localhost:8000/docs.

To re-pull everything from the live sources (rewrites the snapshot and reloads the database):

```bash
docker compose run --rm app python -m tracker.ingest fetch
```

To add or swap a company, edit `config/universe.yaml` and run the same command.

## Running the checks

```bash
docker compose run --rm app python scripts/check.py   # lint, formatting, types (mypy), all 66 tests
```

- `test_xbrl.py`, `test_metrics.py`, `test_filings.py`, `test_narrative.py`, `test_grounding.py`
  and `test_tools.py` cover the data rules, the answer number check and the tool output on small
  hand-made inputs.
- `test_agent.py` covers routing and error handling with a scripted fake model (no API key).
- `test_api.py` checks the API against the real snapshot, one test per question in the brief, plus
  `/ask` over HTTP with real tools and a fake model (swapped in with `dependency_overrides`).
  It needs Postgres, so outside Docker these tests are skipped.
- `test_live.py` is an evaluation, not a unit test: it asks the configured **real** model the
  brief's six questions and checks the route, the tools called, the expected figures and the
  decline. It costs about 15 LLM calls, so it only runs on request:
  `docker compose run --rm app pytest -m live`.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | Google AI Studio's OpenAI-compatible endpoint | Any `/chat/completions` endpoint with tool calling |
| `LLM_API_KEY` | *(empty)* | Without it, `/ask` returns a clear 503 and everything else works |
| `LLM_MODEL` | `gemini-3.7-flash` | Must support tool calling |
| `SEC_USER_AGENT` | placeholder | SEC asks for contact details; only used by a live `fetch` |
| `ASK_TIMEOUT_SECONDS` | `90` | Time budget for one question, across all its LLM calls (504 when exceeded) |
| `ASK_CONCURRENCY` | `8` | Questions answered at once; more are refused with a 429 |

**To use your own model or proxy,** set the three `LLM_` variables in `.env` and run
`docker compose up -d`. No code changes are needed.

**Provider and model I used:** Google AI Studio (free tier), `gemini-3.7-flash`, through its
OpenAI-compatible endpoint. The free tier allows about 20 requests per model per day, so one of the six
example questions was run on `gemini-3.5-flash` instead (noted in [`docs/EXAMPLES.md`](docs/EXAMPLES.md)).

## Using the API

| Method | Path | Returns |
|---|---|---|
| `GET` | `/companies`, `/companies/{ticker}` | Covered companies, with the fiscal years, 10-Ks and prices on file |
| `GET` | `/companies/{ticker}/fundamentals?years=N` | Revenue, gross profit, operating income, net income, diluted EPS, margins and YoY growth per fiscal year, with the SEC source of each value |
| `GET` | `/companies/{ticker}/prices?start=&end=` | Daily closes |
| `GET` | `/companies/{ticker}/valuation` | Trailing P/E: latest close ÷ latest annual diluted EPS |
| `GET` | `/rankings/{metric}?fiscal_year=` | Every company ranked on one metric, e.g. `/rankings/gross_margin` |
| `POST` | `/ask` | An answer, the route taken, the tools called, sources, and any figures in the answer not found in a tool result (`unverified_numbers`) |
| `GET` | `/health` | `ok` if the database answers |

Every error, including unknown routes and unexpected failures, has one shape, documented in the
OpenAPI spec as `ErrorResponse`:
`{"error": {"code": "NOT_FOUND", "message": "...", "request_id": "..."}}`.

- **404:** unknown ticker or route
- **422:** invalid input (a bad ticker, metric or parameter)
- **429:** too many questions in flight, or the LLM provider is rate-limiting, with `Retry-After`
- **503:** the LLM isn't configured or reachable
- **504:** no answer within `ASK_TIMEOUT_SECONDS`
- **500:** a bug, logged, with no internals in the response

Every response carries an `X-Request-ID` header (yours, if you send one), and errors include it,
so a report can be matched to the server logs.

### Example: the cross-source join

```bash
curl localhost:8000/companies/AAPL/valuation
```
```json
{"ticker": "AAPL", "price_date": "2026-10-07", "close": 336.67, "fiscal_year": 2025,
 "period_end": "2025-09-27", "eps_diluted": 7.46, "trailing_pe": 45.13,
 "eps_accession": "0000320193-25-000079"}
```

### Example: a question that needs numbers and filing text

```bash
curl localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "How did MSFT'\''s revenue grow last year, and what did management attribute it to?"}'
```

`route: both`, using `get_fundamentals` and `search_filings`:

> In fiscal year 2026 (ended June 30, 2026), Microsoft's revenue grew to **$331.84 billion** …
> a **17.8%** increase year-over-year … In its FY2026 10-K MD&A, management attributed the overall
> revenue increase of $50.1 billion primarily to **growth in Microsoft Cloud** … Azure and other
> cloud services grew **41%** …

### Example: a question it should decline

```bash
curl localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "What is the company'\''s forward guidance for next quarter?"}'
```

`route: none`, no tools called:

> Forward guidance, quarterly forecasts, and future quarterly outlooks are not available in the
> provided dataset. … Instead, I can provide historical annual financial performance …

All six of the brief's questions, unedited: [`docs/EXAMPLES.md`](docs/EXAMPLES.md). To run them
yourself: `python scripts/ask_examples.py --base-url http://localhost:8000`.

## How I used AI

I built this with Claude (Claude Code) working alongside me, as the brief expects. I drove the
project, and Claude helped me move faster.

**What I owned:**
- How to read the brief: as a trust problem, with grounding and provenance at the centre.
- The architecture: snapshot-based ingestion, one service layer shared by the API and the agent,
  and the line between what the LLM does and what code does.
- Scope: cutting a first, larger build down to this MVP (see [`docs/MVP.md`](docs/MVP.md)).
- Checking the data against the 10-Ks, and catching the edge cases that needed rules: GOOGL's tag
  change, ETN's missing operating income and relocated MD&A, NVDA's split-restated EPS.
- The final checks: all six example questions against a real model.

**Where Claude helped:**
- Drafting code and tests alongside mine.
- Reviewing my work and suggesting options when a decision was open.
- Carrying out refactors once I'd decided on them.

## Known gaps

- P/E uses the latest *annual* EPS, so it can be up to a year stale; there's no 10-Q data.
- Filing search is keyword-based, so it can miss paraphrases.
- Section extraction is pattern-based. It's checked on these five companies, and it logs and skips a
  section it can't find rather than storing the wrong text.
- ETN's operating income is derived (gross profit − SG&A − R&D), which would be wrong for a company
  with other operating expense lines.
- The answer number check flags figures it can't find in a tool result; it doesn't block them,
  and it also flags correct figures the model restated in other units.
- No auth, no scheduled refresh, no migrations (the schema is applied on start).

## Project layout

```
src/tracker/
  sec.py · xbrl.py · filings.py · prices.py   the three sources: fetch and clean up
  ingest.py                                   fetch -> snapshot -> Postgres; `seed` loads the snapshot
  schema.sql                                  the database schema
  metrics.py · narrative.py                   the math and the 10-K comparison (no database, no LLM)
  models.py                                   typed models: what queries return and the API serves
  service.py                                  queries shared by the API and the agent
  api/                                        the FastAPI app (FastAPI's "Bigger Applications" layout)
    app.py · dependencies.py · errors.py      app factory, injected resources, error responses
    companies.py · rankings.py · questions.py · operations.py    one router each
  agent.py · tools.py                         the Q&A agent and its tools
  grounding.py                                checks the answer's numbers against the tool results
  errors.py                                   the error types and their HTTP status codes
  config.py · db.py
tests/        test_xbrl · test_metrics · test_filings · test_narrative · test_grounding · test_tools
              test_agent · test_api · test_live (real-model evaluation, opt-in) · fakes
scripts/      check.py (all checks) · ask_examples.py (the brief's questions)
docs/         BRIEF.md · MVP.md · DESIGN.md · EXAMPLES.md
data/         snapshot/ (committed data, ~370 KB)
config/       universe.yaml
```
