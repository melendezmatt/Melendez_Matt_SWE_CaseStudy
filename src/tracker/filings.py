"""Find a company's latest 10-Ks and pull out Item 1A (Risk Factors) and Item 7 (MD&A).

A 10-K is one long HTML page. We flatten it to text, one line per paragraph, then take the
text between a section's heading and the next section's heading. The headings also appear in
the table of contents, so we take the *longest* match: the TOC entry encloses almost nothing.
"""

import re
import warnings
from collections import Counter

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# 10-Ks are XHTML; the forgiving HTML parser reads them fine, so silence its warning.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

FILINGS_PER_COMPANY = 2  # the brief asks for the latest two annual reports
MIN_SECTION_CHARS = 5_000  # anything shorter is a TOC entry or a cross-reference, not the section
CHUNK_CHARS = 1_500

PARAGRAPH_TAGS = ["p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table"]

GAP = r"[\s.:\-–—]*"  # what can sit between "Item", "1A" and the title: spaces, dots, dashes
MDNA_TITLE = (
    r"management.s\s+discussion\s+and\s+analysis\s+of\s+financial\s+condition"
    r"\s+and\s+results\s+of\s+operations"
)


def heading(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.MULTILINE)


SECTION_TITLES = {"risk_factors": "Item 1A Risk Factors", "mdna": "Item 7 MD&A"}

# Section -> list of (start heading, end heading), tried in order.
SECTIONS = {
    "risk_factors": [
        (heading(rf"^item{GAP}1a\b{GAP}risk\s+factors"), heading(rf"^item{GAP}(1b|1c|2)\b")),
    ],
    "mdna": [
        (heading(rf"^item{GAP}7\b{GAP}management"), heading(rf"^item{GAP}(7a|8)\b")),
        # ETN's Item 7 just says "see MD&A", which sits after the financial statements under
        # its own all-caps heading and runs until the market-risk section.
        (
            heading(rf"^{MDNA_TITLE}\.?$"),
            heading(r"^(market\s+risk\s+disclosure|quantitative\s+and\s+qualitative|item\s*(7a|8|9)\b)"),
        ),
    ],
}


def latest_10ks(submissions: dict) -> list[dict]:
    """The company's most recent original 10-Ks, newest first. Amendments (10-K/A) are skipped."""
    recent = submissions["filings"]["recent"]
    filings = [
        {"accession": acc, "filed": filed, "period_end": period_end, "document": doc}
        for acc, form, filed, period_end, doc in zip(
            recent["accessionNumber"],
            recent["form"],
            recent["filingDate"],
            recent["reportDate"],
            recent["primaryDocument"],
            strict=True,
        )
        if form == "10-K"
    ]
    filings.sort(key=lambda f: f["filed"], reverse=True)
    return filings[:FILINGS_PER_COMPANY]


def html_to_text(html: str) -> str:
    """One line per paragraph, with hidden XBRL data and page headers/footers removed."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "ix:header"]):  # ix:header is hidden XBRL data
        tag.decompose()
    for tag in soup.find_all(PARAGRAPH_TAGS):
        tag.insert_after("\n")
    for cell in soup.find_all(["td", "th"]):
        cell.insert_after(" ")

    text = soup.get_text().replace("\xa0", " ")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(drop_page_furniture([line for line in lines if line]))


def drop_page_furniture(lines: list[str]) -> list[str]:
    """Remove page numbers and running headers/footers such as "Apple Inc. | 2024 Form 10-K | 26".

    A footer differs only in its page number, so lines are compared with digits masked. A short
    line that repeats 8+ times is furniture. All-number lines (table rows) are never dropped.
    """

    def masked(line: str) -> str:
        return re.sub(r"\d+", "#", line)

    counts = Counter(masked(line) for line in lines if len(line) < 80)
    furniture = {m for m, n in counts.items() if n >= 8 and re.search(r"[A-Za-z]", m)}
    return [
        line
        for line in lines
        if masked(line) not in furniture and not re.fullmatch(r"(page\s*)?\d{1,3}", line, re.I)
    ]


def extract_section(text: str, section: str) -> str | None:
    for start_heading, end_heading in SECTIONS[section]:
        longest = ""
        for start in start_heading.finditer(text):
            end = end_heading.search(text, start.end())
            candidate = text[start.start() : end.start() if end else len(text)]
            longest = max(longest, candidate, key=len)
        if len(longest) >= MIN_SECTION_CHARS:
            return longest.strip()
    return None


def chunk(text: str, max_chars: int = CHUNK_CHARS) -> list[str]:
    """Pack whole paragraphs into chunks of up to max_chars. A paragraph longer than that on its
    own is split at the last sentence end that fits."""
    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n"):
        while len(paragraph) > max_chars:
            cut = paragraph.rfind(". ", 0, max_chars) + 1 or max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if current and len(current) + 1 + len(paragraph) > max_chars:
            chunks.append(current)
            current = ""
        current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks
