"""XBRL normalization: each of the messy-data rules in xbrl.py, on small hand-made inputs."""

from tracker.xbrl import latest_reported_year, normalize


def fact(
    start: str, end: str, val: float, filed: str, accn: str = "a1", form: str = "10-K", fy: int | None = None
) -> dict:
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "accn": accn, "fy": fy}


def company_facts(**tags: list[dict]) -> dict:
    unit = lambda tag: "USD/shares" if tag.startswith("EarningsPerShare") else "USD"  # noqa: E731
    return {"facts": {"us-gaap": {tag: {"units": {unit(tag): facts}} for tag, facts in tags.items()}}}


def values(rows: list[dict], metric: str) -> dict[str, float]:
    return {r["period_end"]: r["value"] for r in rows if r["metric"] == metric}


FY2024 = ("2024-01-01", "2024-12-31")


def test_quarterly_figures_inside_a_10k_are_ignored() -> None:
    rows = normalize(
        company_facts(
            Revenues=[
                fact("2024-10-01", "2024-12-31", 30, "2025-02-01"),
                fact(*FY2024, 100, "2025-02-01"),
            ]
        ),
        "X",
    )
    assert values(rows, "revenue") == {"2024-12-31": 100}


def test_latest_filing_wins_so_restatements_are_used() -> None:
    rows = normalize(
        company_facts(
            EarningsPerShareDiluted=[
                fact(*FY2024, 11.90, "2025-02-01", accn="original"),
                fact(*FY2024, 1.19, "2026-02-01", accn="after-10-for-1-split"),
            ]
        ),
        "X",
    )
    [eps] = [r for r in rows if r["metric"] == "eps_diluted"]
    assert eps["value"] == 1.19 and eps["accession"] == "after-10-for-1-split"


def test_fallback_tags_are_resolved_year_by_year() -> None:
    rows = normalize(
        company_facts(
            Revenues=[fact(*FY2024, 200, "2025-02-01")],
            RevenueFromContractWithCustomerExcludingAssessedTax=[
                fact("2023-01-01", "2023-12-31", 150, "2024-02-01"),
                fact(*FY2024, 199, "2025-02-01"),
            ],
        ),
        "X",
    )
    # 2023 only exists under the fallback tag; in 2024 the first tag in the list wins.
    assert values(rows, "revenue") == {"2023-12-31": 150, "2024-12-31": 200}


def test_untagged_subtotals_are_derived_and_labelled() -> None:
    rows = normalize(
        company_facts(
            Revenues=[fact(*FY2024, 1000, "2025-02-01")],
            CostOfRevenue=[fact(*FY2024, 600, "2025-02-01")],
            SellingGeneralAndAdministrativeExpense=[fact(*FY2024, 150, "2025-02-01")],
            ResearchAndDevelopmentExpense=[fact(*FY2024, 50, "2025-02-01")],
        ),
        "X",
    )
    by_metric = {r["metric"]: r for r in rows}
    assert by_metric["gross_profit"]["value"] == 400
    assert by_metric["operating_income"]["value"] == 200
    assert by_metric["operating_income"]["concept"].startswith("derived: us-gaap:Revenues - ")
    assert "cost_of_revenue" not in by_metric  # inputs to derivations aren't stored


def test_a_tagged_subtotal_is_never_overwritten_by_a_derived_one() -> None:
    rows = normalize(
        company_facts(
            Revenues=[fact(*FY2024, 1000, "2025-02-01")],
            CostOfRevenue=[fact(*FY2024, 600, "2025-02-01")],
            GrossProfit=[fact(*FY2024, 410, "2025-02-01")],
        ),
        "X",
    )
    assert values(rows, "gross_profit") == {"2024-12-31": 410}


def test_fiscal_year_is_the_year_the_period_ends() -> None:
    # NVDA's year ending January 2025 is its FY2025.
    rows = normalize(company_facts(Revenues=[fact("2024-01-29", "2025-01-26", 130, "2025-02-26")]), "NVDA")
    assert rows[0]["fiscal_year"] == 2025


def test_a_zero_is_not_reported_so_the_next_tag_is_used() -> None:
    # ETN's 2013-2016 10-Ks tag Revenues as 0; the real figure is under SalesRevenueNet.
    rows = normalize(
        company_facts(
            Revenues=[fact(*FY2024, 0, "2025-02-01")],
            SalesRevenueNet=[fact(*FY2024, 220, "2025-02-01")],
        ),
        "X",
    )
    assert values(rows, "revenue") == {"2024-12-31": 220}


def test_a_subtotal_untagged_in_any_year_is_derived_in_every_year() -> None:
    # Tagged in 2023 but not 2024: both years use the formula, so the series has one definition.
    fy2023 = ("2023-01-01", "2023-12-31")
    rows = normalize(
        company_facts(
            Revenues=[fact(*fy2023, 900, "2024-02-01"), fact(*FY2024, 1000, "2025-02-01")],
            CostOfRevenue=[fact(*fy2023, 500, "2024-02-01"), fact(*FY2024, 600, "2025-02-01")],
            GrossProfit=[fact(*fy2023, 450, "2024-02-01")],
        ),
        "X",
    )
    assert values(rows, "gross_profit") == {"2023-12-31": 400, "2024-12-31": 400}
    assert all(r["concept"].startswith("derived: ") for r in rows if r["metric"] == "gross_profit")


def test_latest_reported_year_is_the_label_in_the_latest_10k() -> None:
    # A retailer whose "fiscal 2024" ends in February 2025: the calendar-year label would say 2025.
    facts = company_facts(
        Revenues=[
            fact("2023-02-01", "2024-02-03", 100, "2024-03-01", fy=2023),
            fact("2024-02-04", "2025-02-01", 110, "2025-03-01", fy=2024),
            fact("2023-02-01", "2024-02-03", 100, "2025-03-01", fy=2024),  # comparative, same filing
        ]
    )
    assert latest_reported_year(facts) == ("2025-02-01", 2024)
