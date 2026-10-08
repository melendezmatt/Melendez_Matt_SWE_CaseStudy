"""Check that the numbers in an answer appear in the tool results it was written from.

The tools pre-format every figure and the prompt says to copy them, but nothing forced the model
to. This catches the failure that matters most to an analyst: a number the model calculated,
converted or remembered. It flags rather than blocks, because a flagged number can still be right
(e.g. "$331.84 billion" restated as "$331,839 million").

Numbers are compared by value, so "$130.50B", "130.5 billion" and "130.50" all match. Years,
dates, list numbering and small counts ("three fiscal years", "Q1") aren't checked: they're not
figures, and checking them would flag nearly every answer.
"""

import re

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A number not glued to a word ("FY2026", "H20" and "D:5" are labels) and what follows it.
NUMBER = re.compile(r"(?<![\w.:])(\d[\d,]*(?:\.\d+)?)(\s*%|x\b)?")


def normalized(number: str) -> str:
    """One spelling per value: "1,234.50" -> "1234.5"."""
    plain = number.replace(",", "")
    return plain.rstrip("0").rstrip(".") if "." in plain else plain.lstrip("0") or "0"


def is_figure(number: str, suffix: str | None) -> bool:
    """True for numbers worth checking: decimals, percentages, multiples, and anything from 100 up
    that isn't a year."""
    if suffix or "." in number:
        return True
    value = int(number.replace(",", ""))
    return value >= 100 and not 1900 <= value <= 2100


def numbers_in(text: str, figures_only: bool = False) -> set[str]:
    found = set()
    for match in NUMBER.finditer(ISO_DATE.sub(" ", text)):
        number, suffix = match.group(1).rstrip(","), match.group(2)
        if number and (not figures_only or is_figure(number, suffix)):
            found.add(normalized(number))
    return found


def unverified_numbers(answer: str, evidence: list[str]) -> list[str]:
    """The figures in `answer` that appear in none of the `evidence` texts, in sorted order."""
    known = set().union(*(numbers_in(text) for text in evidence)) if evidence else set()
    return sorted(numbers_in(answer, figures_only=True) - known, key=float)
