"""The agent loop, with a scripted fake model and stub tools: no network, no database, no API key."""

import json
import time
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from fakes import FakeModel, calls, says

from tracker import agent
from tracker.errors import LLMTimeout
from tracker.models import SourceRef
from tracker.tools import FILINGS, NUMBERS, Tool


class FakePool:
    """Counts connections handed out and how many are open at once."""

    def __init__(self) -> None:
        self.checkouts = 0
        self.open = 0

    @contextmanager
    def connection(self):
        self.checkouts += 1
        self.open += 1
        try:
            yield MagicMock()
        finally:
            self.open -= 1


XBRL = SourceRef(label="MSFT FY2026 10-K financial data (SEC XBRL)", url="https://sec/xbrl", accession="a1")
MDNA = SourceRef(label="MSFT FY2026 10-K, Item 7 MD&A", url="https://sec/10k", accession="a1")


def numbers(conn, sources):
    sources += [XBRL, XBRL]  # cited twice, listed once
    return {"revenue": "$331.84B"}


def filings(conn, sources):
    sources.append(MDNA)
    return {"passages": ["Azure grew 34%."]}


def broken(conn, sources):
    raise ValueError("metric must be one of ...")


def buggy(conn, sources):
    raise KeyError("revenue")  # a bug in a tool, not bad arguments


@pytest.fixture(autouse=True)
def stub_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    stubs = [
        Tool(numbers, NUMBERS, "", {}, ()),
        Tool(filings, FILINGS, "", {}, ()),
        Tool(broken, NUMBERS, "", {}, ()),
        Tool(buggy, NUMBERS, "", {}, ()),
    ]
    monkeypatch.setattr(agent, "TOOLS", {tool.run.__name__: tool for tool in stubs})
    monkeypatch.setattr(agent, "system_prompt", lambda pool: "system prompt")


def test_numbers_plus_narrative_question_routes_to_both() -> None:
    model = FakeModel(calls("numbers", "filings"), says("Revenue grew; management cited Azure."))
    result = agent.ask(model, FakePool(), "How did MSFT's revenue grow, and why?")
    assert result.route == "both"
    assert [c.tool for c in result.tool_calls] == ["numbers", "filings"]
    assert result.sources == [
        "MSFT FY2026 10-K financial data (SEC XBRL)",
        "MSFT FY2026 10-K, Item 7 MD&A",
    ]
    assert result.source_refs == [XBRL, MDNA]  # with links, de-duplicated
    # each tool result went back to the model, matched to its call
    tool_messages = [m for m in model.requests[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_messages] == ["id-numbers", "id-filings"]


def test_a_connection_is_held_only_while_a_tool_runs() -> None:
    pool = FakePool()

    class Watcher(FakeModel):
        def complete(self, messages: list[dict], tools: list[dict] | None, timeout: float) -> dict:
            assert pool.open == 0, "a connection was held while waiting on the model"
            return super().complete(messages, tools, timeout)

    agent.ask(Watcher(calls("numbers", "filings"), says("done")), pool, "question")
    assert pool.checkouts == 2  # one per tool call


def test_out_of_scope_question_uses_no_data() -> None:
    model = FakeModel(says("I don't have forward guidance."))
    result = agent.ask(model, FakePool(), "What is the guidance for next quarter?")
    assert result.model_dump() == {
        "answer": "I don't have forward guidance.",
        "route": "none",
        "tool_calls": [],
        "sources": [],
        "source_refs": [],
        "unverified_numbers": [],
    }


def test_tool_errors_go_back_to_the_model_instead_of_failing() -> None:
    model = FakeModel(calls("broken", "no_such_tool"), says("That metric isn't available."))
    result = agent.ask(model, FakePool(), "Rank by something odd")
    assert [c.ok for c in result.tool_calls] == [False, False]
    assert result.route == "none"  # failed calls don't count as using data
    errors = [json.loads(m["content"]) for m in model.requests[1]["messages"] if m["role"] == "tool"]
    assert all("error" in e for e in errors)


def test_a_crashing_tool_is_reported_to_the_model_not_the_caller() -> None:
    model = FakeModel(calls("buggy", "numbers"), says("Revenue was $331.84B."))
    result = agent.ask(model, FakePool(), "MSFT revenue?")
    assert [c.ok for c in result.tool_calls] == [False, True]
    assert result.answer == "Revenue was $331.84B." and result.route == "numbers"


def test_numbers_missing_from_the_tool_results_are_flagged() -> None:
    model = FakeModel(calls("numbers"), says("Revenue was $331.84B, up 18.2% on $280.6B."))
    result = agent.ask(model, FakePool(), "MSFT revenue growth?")
    assert result.unverified_numbers == ["18.2%", "$280.6B"]  # $331.84B came from the tool
    assert result.answer.endswith("verify them before relying on them: 18.2%, $280.6B.")


def test_a_figure_from_the_question_is_not_evidence() -> None:
    model = FakeModel(calls("numbers"), says("No: revenue was $331.84B, not $500B."))
    result = agent.ask(model, FakePool(), "Was MSFT's revenue $500B?")
    assert result.unverified_numbers == ["$500B"]


def test_figures_in_an_answer_that_used_no_tools_are_all_flagged() -> None:
    model = FakeModel(says("Next quarter's revenue should be about $85.2B."))
    result = agent.ask(model, FakePool(), "What is the guidance for next quarter?")
    assert result.route == "none" and result.unverified_numbers == ["$85.2B"]


def test_each_model_call_gets_only_the_time_left() -> None:
    model = FakeModel(calls("numbers"), says("done"))
    agent.ask(model, FakePool(), "question", timeout=30)
    first, second = (r["timeout"] for r in model.requests)
    assert 0 < second <= first <= 30


def test_a_question_that_runs_out_of_time_is_stopped() -> None:
    class Slow(FakeModel):
        def complete(self, messages: list[dict], tools: list[dict] | None, timeout: float) -> dict:
            time.sleep(0.05)
            return super().complete(messages, tools, timeout)

    model = Slow(*[calls("numbers")] * agent.MAX_ROUNDS, says("too late"))
    with pytest.raises(LLMTimeout):
        agent.ask(model, FakePool(), "question", timeout=0.08)
    assert len(model.requests) == 2  # stopped before the third call, not after all seven


def test_after_the_last_round_the_model_must_answer_without_tools() -> None:
    model = FakeModel(*[calls("numbers")] * agent.MAX_ROUNDS, says("Final answer."))
    result = agent.ask(model, FakePool(), "Keep calling tools")
    assert result.answer == "Final answer."
    assert model.requests[-1]["tools"] is None


def test_no_api_key_means_no_model() -> None:
    settings = MagicMock(llm_api_key="")
    assert agent.model_from_settings(settings) is None
