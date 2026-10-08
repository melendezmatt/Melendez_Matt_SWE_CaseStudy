"""10-K section extraction on small hand-made documents shaped like the real ones."""

from tracker.filings import chunk, extract_section, html_to_text, latest_10ks

FILLER = "This is a long risk paragraph about supply chains and demand. " * 30


def test_the_section_is_found_and_the_table_of_contents_is_skipped() -> None:
    text = "\n".join(
        [
            "Item 1A. Risk Factors",  # table of contents
            "Item 1B. Unresolved Staff Comments",
            "Item 1A. Risk Factors",  # the real section
            FILLER,
            FILLER,
            FILLER,
            "Item 1B. Unresolved Staff Comments",
            "None.",
        ]
    )
    section = extract_section(text, "risk_factors")
    assert section.startswith("Item 1A. Risk Factors\nThis is a long")
    assert "Unresolved" not in section


def test_mdna_placed_after_the_financial_statements_is_found() -> None:
    # ETN: Item 7 only points elsewhere; the MD&A is a standalone section with an all-caps title.
    text = "\n".join(
        [
            "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations.",
            "Information required by this Item is presented in MD&A of this Form 10-K.",
            "Item 7A. Quantitative and Qualitative Disclosures about Market Risk.",
            "MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS.",
            FILLER,
            FILLER,
            FILLER,
            "MARKET RISK DISCLOSURE",
            "Rates moved.",
        ]
    )
    section = extract_section(text, "mdna")
    assert section.startswith("MANAGEMENT’S") and "Rates moved" not in section


def test_a_missing_section_is_reported_as_missing() -> None:
    assert extract_section("Item 1. Business\nWe sell things.", "risk_factors") is None


def test_html_is_flattened_without_hidden_data_or_page_footers() -> None:
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet".split()
    page = "<div>Body about {w}.</div><div>Acme Inc. | 2024 Form 10-K | {n}</div><div>{n}</div>"
    html = "<ix:header>hidden XBRL facts</ix:header>" + "".join(
        page.format(w=w, n=i) for i, w in enumerate(words)
    )
    assert html_to_text(html).splitlines() == [f"Body about {w}." for w in words]


def test_chunks_keep_paragraphs_whole_and_stay_under_the_limit() -> None:
    paragraphs = [f"Paragraph {i}. " + "word " * 60 for i in range(20)]
    chunks = chunk("\n".join(paragraphs), max_chars=1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert "".join(chunks).replace("\n", "") == "".join(paragraphs)


def test_only_the_two_latest_original_10ks_are_used() -> None:
    recent = {
        "accessionNumber": ["q", "amendment", "k2025", "k2024", "k2023"],
        "form": ["10-Q", "10-K/A", "10-K", "10-K", "10-K"],
        "filingDate": ["2025-05-01", "2025-04-01", "2025-02-01", "2024-02-01", "2023-02-01"],
        "reportDate": ["2025-03-31", "2024-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
        "primaryDocument": ["q.htm", "a.htm", "k25.htm", "k24.htm", "k23.htm"],
    }
    assert [f["accession"] for f in latest_10ks({"filings": {"recent": recent}})] == ["k2025", "k2024"]
