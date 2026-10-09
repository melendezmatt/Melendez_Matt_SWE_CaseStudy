"""The Q&A agent: a tool-calling loop over any OpenAI-compatible chat API.

What the LLM does:
  - routing: decides whether a question needs the numbers, the filing text, both, or neither
  - fills in tool arguments (tickers, years, search keywords)
  - writes the answer from the tool results

What the LLM does not do (it's all plain code):
  - any arithmetic (metrics.py), the risk-factor comparison (narrative.py)
  - the reported route and sources, which come from the tools that actually ran
  - checking the answer's numbers against the tool results, and telling the reader in the answer
    when one isn't there (grounding.py)
"""

import json
import logging
import time
from contextlib import AbstractContextManager
from typing import Any, Protocol

import openai

from tracker import grounding, service
from tracker.config import Settings
from tracker.db import DbConnection
from tracker.errors import AppError, LLMRateLimited, LLMTimeout, LLMUnavailable
from tracker.models import Answer, Route, SourceRef, ToolCall
from tracker.tools import FILINGS, NUMBERS, TOOLS

log = logging.getLogger(__name__)

MAX_ROUNDS = 6  # tool-calling rounds before the agent must answer with what it has
ASSISTANT_FIELDS = ("role", "content", "tool_calls")  # what every OpenAI-compatible API accepts back

SYSTEM_PROMPT = """\
You answer questions from portfolio managers and analysts about a fixed set of public companies, \
using only the tools provided. The tools return data from SEC 10-K filings (financial figures, \
and the text of Item 1A Risk Factors and Item 7 MD&A) and daily closing prices.

Data available:
{coverage}

Rules:
1. Every number, and every claim about what a filing says, must come from a tool result in this \
conversation. Don't use outside knowledge about these companies, even if you think it's right.
2. Choose tools by what the question needs: figures, rankings or valuation -> number tools; what \
management said, drivers or risks -> filing tools; "how did X change and why" -> both.
3. Copy numbers exactly as the tools format them. Don't calculate new ones.
4. If the data isn't available (forward guidance, outlook, forecasts, estimates, quarterly results, \
other companies), say so plainly and say what you can provide instead. Never guess.
5. "Last year" means each company's latest fiscal year. Fiscal years end on different dates for \
different companies; say so when comparing companies.
6. Be concise: lead with the answer. When summarizing a filing, attribute it, e.g. "In its FY2025 \
10-K MD&A, management attributed ...".
7. If a tool result says it is truncated, either fetch more or say plainly that the answer covers \
only part of it (e.g. "the largest 20 of 31 new paragraphs"). Never present a partial list as complete.
"""


class ChatModel(Protocol):
    """Takes messages and tools; returns text or tool calls. Tests use a scripted fake.
    `timeout` is the time left for the whole question, in seconds."""

    def complete(self, messages: list[dict], tools: list[dict] | None, timeout: float) -> dict: ...


class ConnectionPool(Protocol):
    def connection(self) -> AbstractContextManager[DbConnection]: ...


class OpenAICompatible:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.model = model
        # No automatic retries: each call gets only what's left of the question's time budget, and a
        # retry would overrun it. Rate limits go back to the caller with the provider's Retry-After.
        self.client = openai.OpenAI(base_url=base_url, api_key=api_key, max_retries=0)

    def complete(self, messages: list[dict], tools: list[dict] | None, timeout: float) -> dict:
        # Messages are plain dicts in OpenAI's wire format; the SDK's TypedDicts add nothing here.
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "timeout": timeout,
        }
        if tools:
            request["tools"] = tools
        try:
            response = self.client.chat.completions.create(**request)
        except openai.RateLimitError as exc:
            raise LLMRateLimited(
                "the LLM provider is rate-limiting requests; try again shortly",
                retry_after=exc.response.headers.get("retry-after"),
            ) from exc
        except openai.APITimeoutError as exc:
            raise LLMTimeout("the LLM did not answer within the time budget") from exc
        except openai.APIError as exc:
            raise LLMUnavailable(f"the LLM call failed: {exc}") from exc
        message = response.choices[0].message
        raw = message.model_dump(exclude_none=True)
        return {
            "text": message.content,
            "tool_calls": [
                {"id": c.id, "name": c.function.name, "arguments": c.function.arguments}
                for c in message.tool_calls or []
            ],
            # Sent back on the next turn. Tool calls go back exactly as received: Gemini 3 rejects
            # tool results unless the "thought signatures" it attaches to each call come back.
            # Other top-level fields are dropped, because some providers reject the extras they
            # add themselves (e.g. a `reasoning` field) when they're sent back.
            "raw": {key: value for key, value in raw.items() if key in ASSISTANT_FIELDS},
        }


def model_from_settings(settings: Settings) -> OpenAICompatible | None:
    """None when no API key is configured: /ask then answers 503 and everything else works."""
    if not settings.llm_api_key:
        return None
    return OpenAICompatible(settings.llm_base_url, settings.llm_api_key, settings.llm_model)


def system_prompt(pool: ConnectionPool) -> str:
    with pool.connection() as conn:
        coverage = service.companies(conn)
    lines = [
        f"- {c.ticker} ({c.name}): financials FY{c.first_fiscal_year}-FY{c.latest_fiscal_year}; "
        f"10-K text for FY{' and FY'.join(map(str, c.filing_fiscal_years))}; "
        f"prices to {c.latest_price_date}"
        for c in coverage
    ]
    return SYSTEM_PROMPT.format(coverage="\n".join(lines))


def ask(model: ChatModel, pool: ConnectionPool, question: str, timeout: float = 90) -> Answer:
    """Answer one question within `timeout` seconds, across every round, or raise LLMTimeout.
    A database connection is held only while a tool runs, never while waiting on the model, so
    slow LLM calls can't exhaust the pool."""
    deadline = time.monotonic() + timeout

    def time_left() -> float:
        left = deadline - time.monotonic()
        if left <= 0:
            raise LLMTimeout(f"no answer within {timeout:g} seconds; try a narrower question")
        return left

    messages = [{"role": "system", "content": system_prompt(pool)}, {"role": "user", "content": question}]
    schemas = [tool.schema for tool in TOOLS.values()]
    calls: list[ToolCall] = []
    sources: list[SourceRef] = []
    used: set[str] = set()
    # Everything the answer may take numbers from: tool results only. Not the question, so a
    # figure the user supplied ("was revenue $500B?") isn't verified by being repeated back.
    evidence: list[str] = []
    # Tools whose last result was cut off (the model stopped paging). The prompt tells the model to
    # say so; this makes sure the reader is told even when it doesn't.
    partial: dict[str, str] = {}

    for _ in range(MAX_ROUNDS):
        reply = model.complete(messages, schemas, time_left())
        if not reply["tool_calls"]:
            answer = reply["text"]
            break
        messages.append(reply.get("raw") or assistant_message(reply))
        for call in reply["tool_calls"]:
            result, ok = run_tool(pool, sources, call["name"], call["arguments"])
            calls.append(ToolCall(tool=call["name"], arguments=call["arguments"], ok=ok))
            if ok:
                used.add(TOOLS[call["name"]].category)
                if result.get("truncated") and result.get("partial_note"):
                    partial[call["name"]] = result["partial_note"]
                else:
                    partial.pop(call["name"], None)
            content = json.dumps(result, default=str)
            evidence.append(content)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    else:
        # Out of rounds: one last call with no tools forces an answer from what's been gathered.
        messages.append({"role": "user", "content": "Answer now from the tool results above."})
        answer = model.complete(messages, None, time_left())["text"]

    answer = (answer or "").strip()
    unverified = grounding.unverified_numbers(answer, evidence)
    if unverified:
        log.warning("answer has numbers not found in any tool result: %s", unverified)
        answer = f"{answer}\n\n{grounding.caveat(unverified)}"
    for note in partial.values():
        log.info("answer was written from a cut-off tool result; note appended")
        answer = f"{answer}\n\nNote: {note}"
    return Answer(
        answer=answer,
        route=route(used),
        tool_calls=calls,
        sources=list(dict.fromkeys(s.label for s in sources)),  # de-duplicated, in order
        source_refs=list(dict.fromkeys(sources)),
        unverified_numbers=unverified,
    )


def assistant_message(reply: dict) -> dict:
    """The model's tool-call turn in OpenAI message format, for models that don't return one."""
    return {
        "role": "assistant",
        "content": reply["text"],
        "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in reply["tool_calls"]
        ],
    }


def run_tool(pool: ConnectionPool, sources: list[SourceRef], name: str, arguments: str) -> tuple[dict, bool]:
    """Run one tool on its own connection. Errors go back to the model as text, so it can fix its
    call or say it can't answer, instead of the whole request failing."""
    if name not in TOOLS:
        return {"error": f"there is no tool called {name}"}, False
    try:
        # A null argument means "not given": drop it so the tool's own default applies.
        given = {key: value for key, value in json.loads(arguments or "{}").items() if value is not None}
        with pool.connection() as conn:
            return TOOLS[name].run(conn, sources, **given), True
    except (AppError, ValueError, TypeError) as exc:  # bad arguments or missing data, not bugs
        log.info("tool %s failed: %s", name, exc)
        return {"error": str(exc)}, False
    except Exception:
        # A bug. Log it in full, but let the model answer from the other tools rather than failing
        # the whole question; the failed call is still reported in `tool_calls`.
        log.exception("tool %s crashed with arguments %s", name, arguments)
        return {"error": f"{name} failed with an internal error; don't retry it"}, False


def route(used: set[str]) -> Route:
    if used == {NUMBERS, FILINGS}:
        return "both"
    if used == {NUMBERS}:
        return "numbers"
    if used == {FILINGS}:
        return "filings"
    return "none"
