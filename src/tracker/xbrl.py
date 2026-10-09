"""Turn SEC XBRL "company facts" into one clean value per company, metric and fiscal year.

The raw data is messy in five ways, each handled here:

1. 10-K filings also contain quarterly figures. Only facts covering a full year (340-390 days)
   are kept.
2. Each 10-K repeats the prior years as comparatives, sometimes restated. The most recently
   filed value wins. That includes EPS restated after a stock split.
3. Companies change tags over time (GOOGL moved revenue to a different tag in 2023), so each
   metric lists fallback tags, tried in order for each year separately.
4. Some companies don't tag a subtotal (GOOGL: gross profit; ETN: operating income since 2020).
   It's derived from its parts, and the `concept` column says so. If any year needs deriving,
   every year is derived, so a company's series never switches definition partway (ETN's
   tagged 2019 operating income was $0.8B above what the formula gives for the same year).
5. Companies sometimes tag a full-year figure as exactly zero (ETN's 2013-2016 10-Ks report
   `Revenues` = 0). A zero is treated as not reported, so the next tag in the list is used.

A fiscal year is labelled by the calendar year it ends in. That's how all five companies label
their own years (NVDA's FY2025 ended January 2025). SEC's `fy` field was tried first and dropped:
it describes the filing, not the period, and older filings get it wrong. It is still used as a
check: `latest_reported_year` gives the label the company's latest 10-K uses, and ingestion warns
if the two disagree (e.g. a retailer whose "fiscal 2024" ends in early 2025).
"""

from datetime import date

ANNUAL_FORMS = {"10-K", "10-K/A"}

# Metric -> (unit, XBRL tags in priority order).
METRICS: dict[str, tuple[str, list[str]]] = {
    "revenue": (
        "USD",
        [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:SalesRevenueNet",
        ],
    ),
    "cost_of_revenue": (
        "USD",
        [
            "us-gaap:CostOfRevenue",
            "us-gaap:CostOfGoodsAndServicesSold",
        ],
    ),
    "gross_profit": ("USD", ["us-gaap:GrossProfit"]),
    "sga": ("USD", ["us-gaap:SellingGeneralAndAdministrativeExpense"]),
    "rnd": ("USD", ["us-gaap:ResearchAndDevelopmentExpense"]),
    "operating_income": ("USD", ["us-gaap:OperatingIncomeLoss"]),
    "net_income": ("USD", ["us-gaap:NetIncomeLoss"]),
    "eps_diluted": ("USD/shares", ["us-gaap:EarningsPerShareDiluted"]),
}

# Subtotals derived when untagged: metric -> (start from, subtract these).
DERIVED = {
    "gross_profit": ("revenue", ["cost_of_revenue"]),
    "operating_income": ("gross_profit", ["sga", "rnd"]),
}

# Inputs to the derivations; needed during normalization but not stored.
INPUT_ONLY = {"cost_of_revenue", "sga", "rnd"}


def annual_values(facts: dict, tag: str, unit: str) -> dict[str, dict]:
    """Full-year values for one tag, keyed by period end date: the latest-filed value for each."""
    taxonomy, name = tag.split(":")
    entries = facts["facts"].get(taxonomy, {}).get(name, {}).get("units", {}).get(unit, [])

    by_end: dict[str, list[dict]] = {}
    for e in entries:
        if e.get("form") not in ANNUAL_FORMS or "start" not in e or e["val"] == 0:
            continue
        days = (date.fromisoformat(e["end"]) - date.fromisoformat(e["start"])).days
        if 340 <= days <= 390:
            by_end.setdefault(e["end"], []).append(e)

    out = {}
    for end, group in by_end.items():
        latest = max(group, key=lambda e: e["filed"])
        out[end] = {"value": float(latest["val"]), "accession": latest["accn"], "concept": tag}
    return out


def normalize(facts: dict, ticker: str) -> list[dict]:
    """Rows for the `fundamentals` table."""
    values: dict[str, dict[str, dict]] = {}
    for metric, (unit, tags) in METRICS.items():
        values[metric] = {}
        for tag in tags:
            for end, v in annual_values(facts, tag, unit).items():
                values[metric].setdefault(end, v)  # an earlier tag in the list wins

    for metric, (base, minus) in DERIVED.items():
        derived = {}
        for end, b in values[base].items():
            parts = [values[m][end] for m in minus if end in values[m]]
            if len(parts) < len(minus):
                continue  # an input is missing
            derived[end] = {
                **b,
                "value": b["value"] - sum(p["value"] for p in parts),
                "concept": "derived: "
                + " - ".join(c["concept"].removeprefix("derived: ") for c in [b, *parts]),
            }
        if any(end not in values[metric] for end in derived):
            values[metric] = derived  # some year is untagged: one definition for every year

    return [
        {
            "ticker": ticker,
            "metric": metric,
            "fiscal_year": int(end[:4]),
            "period_end": end,
            "value": v["value"],
            "concept": v["concept"],
            "accession": v["accession"],
        }
        for metric, by_end in values.items()
        if metric not in INPUT_ONLY
        for end, v in sorted(by_end.items())
    ]


def latest_reported_year(facts: dict) -> tuple[str, int] | None:
    """The period end and fiscal year (SEC's `fy`) of the company's latest 10-K, i.e. how the
    company itself labels its most recent year. None if no 10-K carries a fiscal year."""
    latest = None
    for unit, tags in METRICS.values():
        for tag in tags:
            taxonomy, name = tag.split(":")
            for e in facts["facts"].get(taxonomy, {}).get(name, {}).get("units", {}).get(unit, []):
                if (
                    e.get("form") in ANNUAL_FORMS
                    and e.get("fy")
                    and (latest is None or (e["filed"], e["end"]) > (latest["filed"], latest["end"]))
                ):
                    latest = e
    return (latest["end"], int(latest["fy"])) if latest else None
