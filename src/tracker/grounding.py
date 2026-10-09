"""Check that the numbers in an answer appear in the tool results it was written from.

The tools pre-format every figure and the prompt says to copy them, but nothing forced the model
to. This catches the failure that matters most to an analyst: a number the model calculated,
converted or remembered. It flags rather than blocks, because a flagged number can still be right.
The flag goes in the answer itself (`caveat`), not only in a response field, so the reader sees it.

Figures are compared by kind and value, not by spelling. "$130.50B", "$130.5 billion" and
"$130,497 million" are the same amount, so they match. "$130.50 million" is 1,000 times smaller,
"130.5%" is a percentage and "130.5x" is a multiple, so none of them match "$130.50B". Rounding is
allowed in both directions: "18%" matches "17.8%", since each figure stands for a range as wide
as its last digit.

A bare number with no unit matches any figure with the same digits. 10-K tables state their units
once in a header ("in millions"), so "$331,839 million" in an answer is found in an MD&A table
that says "331,839".

Years, dates, list numbering and small counts ("three fiscal years", "Q1") aren't checked: they're
not figures, and checking them would flag nearly every answer.
"""

import re
from dataclasses import dataclass

ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A number not glued to a word ("FY2026", "H20" and "D:5" are labels), with its currency sign and
# whatever unit follows it.
NUMBER = re.compile(
    r"(?<![\w.:])(?P<dollar>\$\s?)?(?P<number>\d[\d,]*(?:\.\d+)?)"
    r"(?:(?P<percent>\s?%|(?i:\s+percent(?:age\s+points?)?)\b)"
    r"|(?P<multiple>x)\b"
    r"|(?P<scale>[KMBT]\b|(?i:\s+(?:thousand|million|billion|trillion))\b))?"
)
SCALES = {
    "k": 1e3,
    "thousand": 1e3,
    "m": 1e6,
    "million": 1e6,
    "b": 1e9,
    "billion": 1e9,
    "t": 1e12,
    "trillion": 1e12,
}


@dataclass(frozen=True)
class Figure:
    text: str  # as written, for the caveat
    kind: str  # "percent", "multiple", "amount" (has $ or a scale word) or "plain"
    digits: str  # e.g. "1,234.50"
    scale: float  # 1e9 for "B" or "billion"

    @property
    def number(self) -> float:
        return float(self.digits.replace(",", ""))

    @property
    def decimals(self) -> int:
        return len(self.digits.partition(".")[2])

    @property
    def value(self) -> float:
        return self.number * self.scale

    @property
    def half_step(self) -> float:
        """Half the last digit's place value: "$130.5B" stands for anything from $130.45B to $130.55B."""
        return 0.5 * 10**-self.decimals * self.scale

    def matches(self, other: "Figure") -> bool:
        if "plain" in (self.kind, other.kind):  # no unit on one side: compare the digits
            tolerance = 0.5 * (10**-self.decimals + 10**-other.decimals)
            return abs(self.number - other.number) <= tolerance + 1e-9
        if self.kind != other.kind:
            return False
        return abs(self.value - other.value) <= self.half_step + other.half_step + 1e-9 * abs(self.value)


def normalized(number: str) -> str:
    """One spelling per value: "1,234.50" -> "1234.5"."""
    plain = number.replace(",", "")
    return plain.rstrip("0").rstrip(".") if "." in plain else plain.lstrip("0") or "0"


def is_figure(figure: Figure) -> bool:
    """True for numbers worth checking: anything with a unit, decimals, and whole numbers from 100
    up that aren't years."""
    if figure.kind != "plain" or figure.decimals:
        return True
    return figure.number >= 100 and not 1900 <= figure.number <= 2100


def figures_in(text: str, figures_only: bool = False) -> list[Figure]:
    found = []
    for match in NUMBER.finditer(ISO_DATE.sub(" ", text)):
        digits = match["number"].rstrip(",")
        scale_word = (match["scale"] or "").strip().lower()
        if match["percent"]:
            kind = "percent"
        elif match["multiple"]:
            kind = "multiple"
        elif match["dollar"] or scale_word:
            kind = "amount"
        else:
            kind = "plain"
        figure = Figure(match[0].strip().rstrip(","), kind, digits, SCALES.get(scale_word, 1.0))
        if not figures_only or is_figure(figure):
            found.append(figure)
    return found


def numbers_in(text: str, figures_only: bool = False) -> set[str]:
    """The numbers in `text` as bare digits ("$130.50B" -> "130.5"), for checks that only need the
    digits, such as whether an expected figure appears in an answer."""
    return {normalized(f.digits) for f in figures_in(text, figures_only)}


def unverified_numbers(answer: str, evidence: list[str]) -> list[str]:
    """The figures in `answer`, as written, that match nothing in the `evidence` texts; smallest first."""
    known = [figure for text in evidence for figure in figures_in(text)]
    unverified = {
        figure.text: figure
        for figure in figures_in(answer, figures_only=True)
        if not any(figure.matches(k) for k in known)
    }
    return [text for text, _ in sorted(unverified.items(), key=lambda item: item[1].value)]


def caveat(unverified: list[str]) -> str:
    """The note appended to an answer whose figures include some not found in the data."""
    return (
        "Note: these figures were not found in the data this answer is based on; verify them "
        f"before relying on them: {', '.join(unverified)}."
    )
