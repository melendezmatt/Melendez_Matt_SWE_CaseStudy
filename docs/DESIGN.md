# Design writeup

The first section is the writeup the brief asks for, on one page. The sections after it are the
detail behind each point, for a reviewer who wants it. The [README](../README.md) covers running
it; [MVP.md](MVP.md) maps each requirement to the code.

## Summary

**User and goal.** A PM or analyst asking about a small coverage list, for whom a wrong number is
worse than no answer. So: every number traceable to its SEC filing, no arithmetic by the model, and
a plain "I don't have that" when the data isn't there.

**Architecture and data model.** Ingestion (`fetch`) pulls SEC XBRL facts, the latest two 10-Ks
and Yahoo prices, normalizes them into committed snapshot files, and loads Postgres in one
transaction. Serving shares nothing with ingestion but the database, and `seed` rebuilds it with no
network, so review doesn't depend on SEC or Yahoo. Fundamentals are stored long (company × metric ×
period) with the XBRL tag and filing accession on every value; filing text is stored whole and in
full-text-indexed chunks. Margins, growth and P/E are computed per request in `metrics.py`. The
REST API and the agent's tools call the same `service.py` functions, so they can't disagree.

**Integrating the sources.** XBRL needed five rules, each from a real defect: full-year facts only,
latest filing wins (restatements, NVDA's split), fallback tags per year (GOOGL), zero-tagged values
ignored (ETN), untagged subtotals derived for every year so a series never changes definition.
10-K sections are cut between "Item" headings, taking the longest span to skip the table of
contents. The cross-source join is trailing P/E: latest Yahoo close ÷ latest annual diluted EPS,
both on a split-adjusted basis, returned with the price date and the EPS filing.

**Where the LLM is, and isn't.** The model routes (number tools, filing tools, both, or none),
fills in tool arguments and writes the answer. Code does everything that has to be exact: all
math, number formatting, the year-over-year risk-factor diff, the reported `route` and linked
`source_refs`, and a check of every figure in the answer against the tool results by kind and
value, with any misses listed in the answer itself. Comparisons across companies report how far
apart their fiscal years end. Any OpenAI-compatible endpoint works; no agent framework.

**Trade-offs and cuts.** Annual data only, so P/E can be a year stale (10-Qs are next). One
multiple. Keyword search, not embeddings, so the reviewer's proxy needn't serve an embedding
model. Pattern-based section parsing, checked on these five filers. Figures not found are flagged,
not blocked. No auth, scheduler, migrations or bonus dataset. The full list, with what each would
take, is in [MVP.md](MVP.md#deliberately-left-out).

---

The rest of this document is the detail behind the summary.

## The user and the problem

A PM or analyst wants quick answers about a small coverage list: what a company reported, how it
compares, what it trades at, and what changed in its filings. For that user a wrong number is
worse than no answer. Three goals follow, and they drive the decisions below: **every number
traceable to its filing, no arithmetic by the model, and a plain "I don't have that" when the data
isn't there.**

## Architecture

```
 SEC XBRL ─┐
 SEC 10-Ks ┼─ sec.py / xbrl.py / filings.py / prices.py ─▶ data/snapshot/*.json.gz ─▶ Postgres
 Yahoo    ─┘                (ingest.py fetch)                  (committed)       (ingest.py seed)
                                                                                      │
                                                    metrics.py ─ service.py ◀─────────┘
                                                    narrative.py    │
                                                              ┌─────┴──────┐
                                                           api/        agent.py + tools.py ─ LLM
                                                                             grounding.py
```

**Ingestion and serving share only the database.** Ingestion normalizes everything into
snapshot files first, then loads them into Postgres in one transaction. The snapshot is committed,
so `seed` rebuilds the database with no network access. The reviewer's setup doesn't depend on
SEC or Yahoo being reachable, and a live `fetch` just produces a newer snapshot.

**The REST API and the agent's tools call the same `service.py` functions,** so `/ask` can never
report a different number from `/fundamentals`. Anything the agent can compute, an analyst can
check through REST, e.g. `/rankings/gross_margin` for "which company had the highest margin".

**The API layer is thin and follows FastAPI's "Bigger Applications" layout**: an app factory, one
router per resource, and a `dependencies.py` that supplies the database pool, a connection and the
LLM client (built once at startup; tests swap it with `dependency_overrides`). Tickers and metrics
are validated before any query runs. Every error is an `AppError` subclass that carries its own
status and code, so one handler produces one documented response shape. Unknown routes and crashes
use the same shape. Each response carries an `X-Request-ID`, and a provider's 429 is passed on with
its `Retry-After`.

**Typed end to end.** Queries map rows straight into Pydantic models (`models.py`) with psycopg's
`class_row`. The service layer, the agent's tools and the API all work with those types, and route
functions declare them as return types, so the OpenAPI schema comes from the same definitions. A
renamed column fails at the query, not three layers later, and mypy checks the whole codebase.

## Data model

| Table | Holds | Why this shape |
|---|---|---|
| `companies` | ticker, CIK, name | |
| `fundamentals` | one row per company × metric × fiscal year, with `concept` (XBRL tag) and `accession` (filing) | Long format: a new metric is a line in `xbrl.py`, not a migration. Every number is traceable. |
| `prices` | daily close | Split-adjusted, which matches SEC's split-restated EPS |
| `filings` | the two latest 10-Ks per company: filed date, period covered, URL | |
| `filing_sections` | full Item 1A and Item 7 text | Kept whole for the year-over-year comparison |
| `filing_chunks` | ~1,500-character chunks with a generated full-text index | What `search_filings` queries |

CHECK constraints keep bad data out at the database: a fiscal year must match its period end, a
10-K must be filed after the period it covers, prices must be positive, and sections must be one
of the two we extract.

Margins, growth and P/E are **computed when requested**, not stored. At this size it costs nothing,
there's one source of truth, and a formula fix takes effect without re-ingesting.

## Integrating the three sources

**XBRL is messy, and the rules for it live in one place** (`xbrl.py`):
- 10-Ks also contain quarterly figures, so only facts covering a full year (340–390 days) are kept.
- Every 10-K repeats prior years, sometimes restated, so the latest filing wins. That's also how
  NVDA's EPS comes out on a post-split basis.
- Companies change tags (GOOGL moved revenue to a new tag in 2023), so each metric has fallback
  tags, resolved year by year.
- A full-year figure tagged as exactly zero is treated as not reported, so the next tag is used.
  ETN's 2013–2016 10-Ks tag `Revenues` as 0; without this rule ETN showed $0 revenue for 2011–2016.
- Untagged subtotals are derived and labelled `derived: <formula>`. GOOGL never tags gross profit,
  and ETN stopped tagging operating income in 2020. If any year needs deriving, every year is
  derived, so a series never switches definition partway: ETN's tagged 2019 figure was $0.8B above
  the formula's, which made its margin look like it halved in 2020. ETN's derived figure ties to its reported pretax income once
  interest and other income are added back.
- A fiscal year is the calendar year it ends in, which is how all five companies label their
  years. I first used SEC's `fy` field. It turned out to describe the *filing*, not the period,
  and produced duplicate years for GOOGL and early NVDA data, so I dropped it. It is still used
  as a check: ingestion warns if a company's latest 10-K labels its year differently (a retailer
  whose "fiscal 2024" ends in February 2025 would be labelled 2025 by this rule).
- `tests/test_snapshot.py` checks the committed data itself: revenue positive, margins within
  ±100%, one definition per subtotal per company.

**10-K text** (`filings.py`): the HTML is flattened to one line per paragraph, and page
headers/footers are removed. Each section is the longest stretch between its "Item" heading and the
next one, which skips the table of contents. ETN's Item 7 only points to an MD&A placed after the
financial statements, and a second pattern handles that. All 20 sections extract.

**The cross-source join** (`service.valuation`): trailing P/E = latest Yahoo close ÷ latest annual
diluted EPS from XBRL, as the brief specifies. Both sides are on the same split basis. The response
includes the price date, the fiscal year of the EPS, and the filing it came from.

## Where the LLM is, and where it isn't

| The LLM does | Plain code does |
|---|---|
| **Routing:** picks number tools, filing tools, both, or none | All arithmetic: margins, growth, P/E (`metrics.py`) |
| Fills in tool arguments: tickers, years, search keywords | Number formatting. Tools return `"$130.50B"` and `"71.1%"`, so the model copies instead of converting |
| Writes the answer from the tool results | The risk factor comparison: matching paragraphs across two 10-Ks (`narrative.py`) |
| | The `route` and `sources` in the response, from the tools that actually ran |

The agent is a short tool-calling loop over any OpenAI-compatible API (`agent.py`), so the
reviewer's proxy works by changing three environment variables. No agent framework: the loop is
about 60 lines and easy to inspect. Grounding comes from the system prompt (only tool data, copy
numbers exactly, decline when data is missing, say when a list is partial). The prompt is built
from the database, so it lists exactly which companies, years and filings exist. Tool errors,
including a tool that crashes, go back to the model so it can correct itself or answer from the
other tools, and after 6 rounds it must answer with what it has.

**Grounding is checked, not just requested.** After the model answers, `grounding.py` pulls every
figure out of the answer and looks for it in the tool results by kind and value, not spelling.
`$130.50B`, "$130.5 billion" and "$130,497 million" are the same amount; "$130.50 million",
"130.5%" and "130.5x" are not, so a scale or unit slip (the most common way a model mangles a
number it copies) is caught. Each figure stands for a range as wide as its last digit, so rounding
("18%" for 17.8%) passes. Only tool results count as evidence, not the question, so a figure the
user supplied isn't verified by being repeated back. Any it can't find are returned as
`unverified_numbers`, logged, and listed in a note at the end of the answer, so the reader sees
them. It flags rather than blocks. Known limit: a bare number in a filing passage matches any
figure with the same digits, because 10-K tables state their units once in a header.

**Every answer links to its filings.** `source_refs` lists each SEC filing behind the answer with
its accession number and EDGAR link (and the Yahoo history page for prices). A fiscal year's
figures can come from a later 10-K that restated them, and the link points to that filing, the
one the number was actually taken from.

**Comparisons say when the periods don't line up.** "Last year" means each company's latest fiscal
year, and those can end nine months apart (AAPL in September, MSFT in June). `compare_companies`
returns how far apart the period ends are and, beyond six months, tells the model it must say so.
Fiscal-year labels are a trap for a named year: NVDA's "FY2025" ended in January 2025 and was
mostly 2024. `calendar_year` (on the tool and on `/rankings`) picks each company's fiscal year
whose midpoint falls in that year instead, which puts NVDA's FY2026 next to everyone else's 2025.

**A slow LLM can't stall the rest of the API.** All routes run on one pool of worker threads, so
two limits protect it. Each question has a time budget (`ASK_TIMEOUT_SECONDS`, default 90s) across
all its rounds; each LLM call gets only what's left, with no SDK retries, and a question that runs
out gets a 504. At most `ASK_CONCURRENCY` (default 8) questions run at once; the next is refused
straight away with a 429 rather than queued. A database connection is borrowed only while a tool
runs, never while waiting on the model, so connections are protected too.

**"What new risks were added?"** can't be answered by search: it's a difference between two
documents. Asking a model to compare two 100-page sections is slow and unreliable. `narrative.py`
matches each paragraph to its closest counterpart in the prior year (overlap of three-word phrases,
numbers ignored). The model only summarizes the unmatched ones. They're sorted most novel first and
returned 20 at a time with the totals (NVDA's latest 10-K has 31 new paragraphs), so a cut-off list
still leads with the biggest changes, and the model is told it's partial and can page for more.
The comparison takes about 0.6s on NVDA and is cached by the section texts, so paging is free and
a reload can't serve a stale result.

**Filing search is Postgres full-text search, not embeddings.** It keeps everything in one database
and doesn't assume the reviewer's proxy serves an embedding model. 10-K prose is keyword-heavy, and
the model chooses the keywords. Search defaults to each company's latest 10-K, so "last year"
questions aren't answered from the prior year's MD&A. When both years are searched, a passage
carried over almost word for word is returned once, from the latest 10-K, rather than taking two
of the six result slots.

**What testing with a real model taught me:** Gemini 3 rejects a follow-up request unless the
hidden "thought signature" on each tool call is sent back. The loop now returns the tool calls
exactly as received, but only the standard message fields: other providers add extras of their own
(Groq's `reasoning`) and reject them when they come back, and a reviewer's proxy could be any of
them. The fake model in the unit tests couldn't have caught this. Nor can
it show that routing and declining work, since it's scripted to route. So `pytest -m live` asks a
real model the brief's six questions and checks the route, the tools, the expected figures (read
from the service layer, not hard-coded) and that forward guidance is declined with no tool calls.
Unedited answers from a real model are in [EXAMPLES.md](EXAMPLES.md).

## Trade-offs and cuts

| Decision | Cost |
|---|---|
| Annual data only; P/E on the latest annual EPS (the brief allows it) | P/E can be up to a year stale. 10-Qs are the first thing I'd add, and the table is keyed by period, so they fit. |
| One multiple (P/E) | No P/S: it needs share counts, which are messy for GOOGL's three share classes |
| Keyword search, not semantic | Can miss paraphrases; pgvector would be a drop-in addition |
| Pattern-based section extraction | Checked on these five companies; it logs and skips rather than storing wrong text |
| Derived ETN operating income | Would be wrong for a company with other operating expense lines; labelled as derived, and derived for every year so the series is consistent |
| Fiscal year = calendar year the period ends in | Right for these five; ingestion warns when a new company's own 10-K labels its year differently, rather than relabelling |
| Answer numbers are flagged, not blocked | A flagged figure can still be right; the answer ends with a note listing them, and the analyst decides |
| Fiscal years compared as reported, not re-cut to calendar periods | Without quarterly data a June year can't be re-cut to December; instead the tool measures the gap, warns past six months, and offers `calendar_year` |
| One Docker image for running and checking | It includes the dev tools and tests, so `docker compose run app python scripts/check.py` works; a production image would drop them |
| No auth, scheduler, migrations or bonus dataset | Prototype scope; the time went into getting the three required sources right |

The full list, with what each would take, is in [MVP.md](MVP.md#deliberately-left-out).
