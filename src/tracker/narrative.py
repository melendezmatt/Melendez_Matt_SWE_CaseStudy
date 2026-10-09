"""Year-over-year comparison of a 10-K section, done in code rather than by the LLM.

"What new risks did NVDA add?" is a difference between two documents, so search can't answer
it, and asking an LLM to compare two 100-page sections is slow and unreliable. Instead, each
paragraph in the latest filing is matched to its most similar paragraph in the prior one. A
paragraph with no close match is new. The LLM only summarizes what this module finds.

Similarity is the overlap of three-word phrases (Jaccard similarity). Numbers are ignored, so
"fiscal 2025" becoming "fiscal 2026" doesn't count as a change.
"""

import re
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

MIN_WORDS = 8  # shorter lines are headings or fragments, not statements
NEW_BELOW = 0.35  # best match below this: the paragraph is new
CHANGED_BELOW = 0.75  # between the two: substantially rewritten
# Search chunks are cut at different places in each year's 10-K, so a carried-over passage shares
# less with its counterpart than a whole paragraph would. Measured on the snapshot: 0.5 catches
# about twice as many carried-over chunks as 0.75 (NVDA Item 1A: 68 of 97 vs 49), while only 1 of
# ~30,000 pairs of chunks within one filing reaches it (two near-identical ETN debt notes).
REPEAT_AT = 0.5


def phrases(paragraph: str) -> set[str]:
    words = re.findall(r"[a-z]+", paragraph.lower())
    return {" ".join(words[i : i + 3]) for i in range(max(len(words) - 2, 1))}


def similarity(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n") if len(p.split()) >= MIN_WORDS]


def best_match_scores(paras: list[str], others: list[str]) -> list[float]:
    # Each paragraph's phrases are computed once: inside the loop this took ~4s on NVDA's 10-K.
    other_phrases = [phrases(o) for o in others]
    return [max((similarity(own, o) for o in other_phrases), default=0.0) for own in map(phrases, paras)]


def most_novel_first(paras: list[str], scores: list[float], low: float, high: float) -> list[str]:
    """The paragraphs scoring in [low, high), least like the other filing first. Sorting by novelty,
    not position, means a cut-off list still leads with the biggest changes from every part of
    the section."""
    scored = [(s, p) for p, s in zip(paras, scores, strict=True) if low <= s < high]
    return [p for _, p in sorted(scored, key=lambda sp: sp[0])]


def compare_sections(latest: str, prior: str) -> dict[str, list[str]]:
    """Paragraphs that are new or rewritten in `latest`, and paragraphs dropped from `prior`,
    each list ordered most novel first."""
    latest_paras, prior_paras = paragraphs(latest), paragraphs(prior)
    latest_scores = best_match_scores(latest_paras, prior_paras)
    prior_scores = best_match_scores(prior_paras, latest_paras)
    return {
        "new": most_novel_first(latest_paras, latest_scores, 0.0, NEW_BELOW),
        "changed": most_novel_first(latest_paras, latest_scores, NEW_BELOW, CHANGED_BELOW),
        "removed": most_novel_first(prior_paras, prior_scores, 0.0, NEW_BELOW),
    }


def without_repeats(items: list[T], key: Callable[[T], str]) -> list[T]:
    """`items` in order, dropping any whose text is nearly the same as an earlier one's: the same
    passage carried over from one 10-K to the next, with only its numbers updated."""
    kept: list[tuple[T, set[str]]] = []
    for item in items:
        item_phrases = phrases(key(item))
        if all(similarity(item_phrases, other) < REPEAT_AT for _, other in kept):
            kept.append((item, item_phrases))
    return [item for item, _ in kept]
