"""Test doubles for the LLM: scripted replies, no network, no API key."""


class FakeModel:
    """Returns the replies it's given, in order, and records what it was sent. A reply that is an
    exception is raised instead, to simulate provider failures."""

    def __init__(self, *replies: dict | Exception) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []

    def complete(self, messages: list[dict], tools: list[dict] | None, timeout: float) -> dict:
        self.requests.append({"messages": list(messages), "tools": tools, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def calls(*names: str, arguments: str = "{}") -> dict:
    """A model turn that calls these tools."""
    return {"text": None, "tool_calls": [{"id": f"id-{n}", "name": n, "arguments": arguments} for n in names]}


def says(text: str) -> dict:
    """A model turn that answers."""
    return {"text": text, "tool_calls": []}
