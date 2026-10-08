# Software Engineering Case Study: Fundamentals Tracker

## Prompt

Build a **"Fundamentals Tracker"**: a service that tracks company fundamentals from SEC filings and market data, and answers natural-language questions about both the reported numbers and the narrative in the filings, for a fixed set of five companies.

## Overview

This exercise mirrors the actual work of the role: take a defined, business-adjacent problem and ship a clean, useful backend service with an AI capability on top.

The evaluation focuses on the **engineering rails**: how you ingest and integrate multiple data sources, model and serve the data, and connect an LLM so it answers questions over that data in a grounded way. A basic understanding of financial statements helps, but deep finance knowledge is not required. The financial concepts are deliberately basic (revenue, margins, growth). The filing sections in scope are the plain-English narrative parts, not technical accounting. Your job is to get the model the right data and keep its answers grounded in the source; the model handles interpretation.

There is no single "correct" build, and *how you think* matters far more than feature count. Approach this as if you were building an internal tool that a Portfolio Manager or Analyst would actually use.

## The Companies (fixed universe)

| Ticker | Company   |
|--------|-----------|
| NVDA   | NVIDIA    |
| MSFT   | Microsoft |
| AAPL   | Apple     |
| GOOGL  | Alphabet  |
| ETN    | Eaton     |

The design should **not hardcode** these names. Adding or swapping a ticker should be a configuration change, not a rewrite. Grading uses this fixed set, but generalization is a plus.

## The Data (three required sources)

1. **SEC EDGAR: structured fundamentals (XBRL).** The reported financial-statement facts from EDGAR's XBRL company-facts data. This is the tracker's structured backbone.
2. **SEC EDGAR: filing narrative (text).** The narrative sections of each company's **latest two annual 10-K filings**: Item 1A "Risk Factors" and Item 7 "Management's Discussion & Analysis (MD&A)." These are the readable prose sections; no accounting knowledge is needed to work with them. How you extract this text and make it queryable is your call: precise section parsing and full-text retrieval are both acceptable.
3. **Market data: Yahoo Finance.** Daily or period prices for the five tickers (via `yfinance`, `stooq`, Alpha Vantage free tier, or equivalent). This source is required because at least one derived metric must combine market data with EDGAR fundamentals.

**Optional / bonus:** any freely available alternative dataset that adds value. This part is open to creativity. It is not required, but a strong, well-justified addition is rewarded.

Use public and free sources only. Starting points: SEC EDGAR (structured XBRL APIs at `data.sec.gov`; filing documents via the submissions history) and the market-data libraries above.

## The Task

Build a small, runnable service that does the following:

1. **Ingest from all three sources.** Build a real ingestion pipeline that connects to and pulls from the live sources. This wiring is part of the evaluation.
2. **Persist into PostgreSQL** using a schema you design, covering time-series fundamentals, filing text/sections, and prices. **Also ship a seed/snapshot** of the ingested data (a seed script, committed dump, or pre-populated volume). Reviewers must be able to run and test the service and Q&A layer against stored data **without depending on live API availability at review time.**
3. **Expose a FastAPI service** with a small number of well-structured endpoints serving the fundamentals, prices, and derived metrics.
4. **Compute these metrics:**
   - Reported: revenue, net income, EPS, gross margin, operating margin (free cash flow optional)
   - Derived: year-over-year growth and margins
   - **At least one cross-source valuation multiple** that joins EDGAR and market data (e.g., trailing P/E: current price divided by the latest reported annual EPS, or P/S). Trailing only; no forward estimates.
5. **Add a natural-language / agentic layer** that answers questions using **both** the structured numbers and the filing narrative. The model must do more than free-text chat: use tool use, function calling, structured outputs, retrieval, or an agent loop. The key behavior is **routing**: the system decides whether a question needs the structured numbers, the filing text, or both. The form is your choice (direct LLM API, agent framework, MCP server, etc.). **The writeup must state where the LLM is and isn't in the path, and why.**
   - *No API key?* Several providers offer free tiers with no credit card required, e.g., Google AI Studio (Gemini Flash), Groq (Llama / DeepSeek), OpenRouter (many free models, single endpoint), and GitHub Models. Document the provider and model in the README.
6. **Containerize the whole thing.** `docker compose up` (or a single documented command) must bring up the full stack: app, Postgres, and any other services. The LLM configuration (base URL, API key, model name) must be read from **environment variables** and never hardcoded. Reviewers will point the service at their own LLM proxy and model.

## Constraints

- **Stack:** Python, FastAPI, and PostgreSQL are required, fully containerized via Docker Compose. The AI provider, agent framework, retrieval approach, and all other libraries are your choice.
- **AI-assisted development is expected.** Use whatever tools you normally use. A follow-up session will walk through your decisions, so build it the way you would actually build it.
- **LLM configuration:** base URL, API key, and model name must be configurable via environment variables. The README must **document the provider and exact model(s) used** so reviewers can test like-for-like.
- **Data availability:** ingestion must genuinely connect to the live sources, *and* a persisted snapshot must let everything else run without live API dependency at review time.
- **Time:** about 8–10 hours of work, with 72 hours to submit. The goal is a working prototype, not a production system. Scope deliberately: knowing what to leave out is part of the evaluation, and the follow-up will ask what you cut and why.
- **Finance:** basic familiarity with financial statements helps, but deep expertise is not required. The concepts (revenue, margins, growth, valuation multiples) are entry-level. Period alignment and messy data are expected; how you handle them matters more than perfection.

## Questions the Service Should Handle

The service should answer questions like these (reviewers will test with their own variants):

| Question | Type |
|---|---|
| "What were NVDA's revenue and net income for the last three fiscal years?" | structured |
| "Which of the five companies had the highest gross margin last year?" | derived, comparative |
| "What is AAPL's trailing P/E right now?" | cross-source join |
| "What new risk factors did NVDA add in its latest 10-K versus the prior year?" | filing text |
| "How did MSFT's revenue grow last year, and what did management attribute it to?" | cross-modal: numbers plus MD&A |
| "What is the company's forward guidance for next quarter?" | out of scope: the system should decline or say it lacks that data, not invent an answer |

## Deliverables

1. **A Git repository** containing all code.
2. **A README** that lets reviewers run the full stack with one command and includes:
   - Required environment variables (including the LLM config) and how to point the service at a different model
   - The provider and exact model(s) used
   - 2–3 example interactions, covering both API calls and natural-language queries
3. **A short design writeup** (about 1–2 pages) covering:
   - Architecture and data model: what you built and why
   - How you integrated the three sources, especially the cross-source join
   - Where you used the LLM, where you deliberately didn't, and why
   - Key tradeoffs and what you deliberately left out given the time box

## Evaluation Criteria

| Dimension | What Reviewers Look For |
|---|---|
| **Engineering Quality** | Clean, idiomatic, well-structured Python; sensible project layout; tests, docs, and error handling proportional to a prototype |
| **System Design** | Thoughtful API and data model; sound integration of multiple sources; clear separation of concerns (e.g., ingestion versus serving) |
| **AI Integration** | The model is used where it earns its place (routing, tool use, structured outputs, or retrieval over naive prompting); answers stay grounded; awareness of failure modes and of when *not* to use the model |
| **Product Judgment** | A clear sense of the user and the problem; output that is actually useful |
| **Scope & Pragmatism** | A working prototype with deliberate, well-reasoned cuts |
| **Communication** | Clear README and writeup; reproducible; easy to follow |

## Submission Notes

- Name the files/repo using the format `LastName_FirstName_SWE_CaseStudy`.
- Submit within 72 hours of receiving the case, with an attestation that the work uses only publicly available information and no material non-public information (within the meaning of U.S. federal securities laws) or information subject to a duty or contractual restriction to a third party.
