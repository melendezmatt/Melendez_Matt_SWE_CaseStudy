"""Ingestion: live sources -> snapshot files -> Postgres.

    python -m tracker.ingest fetch    # pull SEC + Yahoo, rewrite data/snapshot/, load the DB
    python -m tracker.ingest seed     # load the DB from data/snapshot/ only (no network)

The snapshot is committed to the repo, so the API and Q&A work even when SEC or Yahoo don't.
Docker runs `seed --if-changed` on start: it loads the snapshot unless the database already holds
that exact snapshot, so pulling a newer one is enough to update an existing database volume.
"""

import argparse
import gzip
import hashlib
import json
import logging
from datetime import date, timedelta
from pathlib import Path

import psycopg
from psycopg.rows import DictRow

from tracker import filings, xbrl
from tracker.config import get_settings, load_tickers
from tracker.db import DbConnection, apply_schema, connect
from tracker.prices import fetch_daily_closes
from tracker.sec import SecClient, document_url

log = logging.getLogger("tracker.ingest")

TABLES = ("companies", "fundamentals", "prices", "filings", "sections")
PRICE_HISTORY_DAYS = 5 * 365


def fetch(tickers: list[str]) -> dict[str, list[dict]]:
    """Pull everything for `tickers` from the live sources, normalized into table rows."""
    sec = SecClient(get_settings().sec_user_agent)
    snapshot: dict[str, list[dict]] = {table: [] for table in TABLES}
    try:
        cik_by_ticker = sec.ticker_to_cik()
        for ticker in tickers:
            cik, name = cik_by_ticker[ticker]
            snapshot["companies"].append({"ticker": ticker, "cik": cik, "name": name})

            log.info("%s: XBRL financials", ticker)
            company_facts = sec.company_facts(cik)
            facts = xbrl.normalize(company_facts, ticker)
            snapshot["fundamentals"] += facts
            warn_if_fiscal_years_mislabelled(ticker, company_facts)

            # Label each 10-K with the fiscal year it reports, using the same labels as the numbers.
            fiscal_year = {f["period_end"]: f["fiscal_year"] for f in facts if f["metric"] == "revenue"}
            for filing in filings.latest_10ks(sec.submissions(cik)):
                log.info("%s: 10-K %s", ticker, filing["accession"])
                text = filings.html_to_text(sec.document(cik, filing["accession"], filing["document"]))
                snapshot["filings"].append(
                    {
                        "accession": filing["accession"],
                        "ticker": ticker,
                        "filed": filing["filed"],
                        "period_end": filing["period_end"],
                        "fiscal_year": fiscal_year.get(filing["period_end"]),
                        "url": document_url(cik, filing["accession"], filing["document"]),
                    }
                )
                for section in filings.SECTIONS:
                    body = filings.extract_section(text, section)
                    if body is None:
                        log.warning("%s %s: %s not found", ticker, filing["accession"], section)
                        continue
                    snapshot["sections"].append(
                        {"accession": filing["accession"], "section": section, "text": body}
                    )

            log.info("%s: prices", ticker)
            start = date.today() - timedelta(days=PRICE_HISTORY_DAYS)
            snapshot["prices"] += fetch_daily_closes(ticker, start)
    finally:
        sec.close()
    return snapshot


def warn_if_fiscal_years_mislabelled(ticker: str, company_facts: dict) -> None:
    """Fiscal years are labelled by the calendar year they end in (see xbrl.py). That matches how
    the covered companies label theirs, but not every company: flag one that doesn't."""
    reported = xbrl.latest_reported_year(company_facts)
    if reported and int(reported[0][:4]) != reported[1]:
        end, fy = reported
        log.warning(
            "%s: its latest 10-K calls the year ending %s FY%s, but it is labelled FY%s here; "
            "fiscal-year labels for this company will be off",
            ticker,
            end,
            fy,
            end[:4],
        )


def write_snapshot(snapshot: dict[str, list[dict]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for table in TABLES:
        with gzip.open(directory / f"{table}.json.gz", "wt", encoding="utf-8") as f:
            json.dump(snapshot[table], f, ensure_ascii=False)
    counts = {table: len(rows) for table, rows in snapshot.items()}
    manifest = {"fetched_on": date.today().isoformat(), "rows": counts}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))


def read_snapshot(directory: Path) -> dict[str, list[dict]]:
    snapshot = {}
    for table in TABLES:
        with gzip.open(directory / f"{table}.json.gz", "rt", encoding="utf-8") as f:
            snapshot[table] = json.load(f)
    return snapshot


def fingerprint(directory: Path) -> str:
    """A hash of the snapshot files: changes whenever the snapshot does."""
    digest = hashlib.sha256()
    for table in TABLES:
        digest.update((directory / f"{table}.json.gz").read_bytes())
    return digest.hexdigest()


def loaded_fingerprint(conn: psycopg.Connection[DictRow]) -> str | None:
    """The fingerprint of the snapshot in the database, or None if it's empty or predates tracking."""
    apply_schema(conn)
    row = conn.execute("SELECT fingerprint FROM snapshot_loaded").fetchone()
    return row["fingerprint"] if row else None


def load(
    conn: DbConnection, snapshot: dict[str, list[dict]], snapshot_fingerprint: str | None = None
) -> None:
    """Replace the database contents with the snapshot, in one transaction: a failed load
    leaves the old data in place."""
    chunks = [
        {"accession": s["accession"], "section": s["section"], "seq": i, "text": text}
        for s in snapshot["sections"]
        for i, text in enumerate(filings.chunk(s["text"]))
    ]
    with conn.transaction():
        apply_schema(conn)
        conn.execute("TRUNCATE companies CASCADE")  # cascades to every other table
        with conn.cursor() as cur:
            insert(cur, "companies", snapshot["companies"])
            insert(cur, "fundamentals", snapshot["fundamentals"])
            insert(cur, "prices", snapshot["prices"])
            insert(cur, "filings", snapshot["filings"])
            insert(cur, "filing_sections", snapshot["sections"])
            # Chunks are rebuilt on every load, so chunking can change without a re-fetch.
            insert(cur, "filing_chunks", chunks)
            cur.execute("DELETE FROM snapshot_loaded")
            if snapshot_fingerprint:
                cur.execute("INSERT INTO snapshot_loaded (fingerprint) VALUES (%s)", (snapshot_fingerprint,))
    log.info("loaded %s", {table: len(rows) for table, rows in snapshot.items()})


def insert(cur: psycopg.Cursor, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    placeholders = ", ".join(f"%({c})s" for c in columns)
    cur.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="python -m tracker.ingest")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="pull from SEC and Yahoo, rewrite the snapshot, load the DB")
    seed = commands.add_parser("seed", help="load the DB from the committed snapshot")
    seed.add_argument(
        "--if-changed", action="store_true", help="do nothing if the DB already holds this snapshot"
    )
    args = parser.parse_args()

    directory = get_settings().snapshot_dir
    if args.command == "fetch":
        snapshot = fetch(load_tickers())
        write_snapshot(snapshot, directory)
    else:
        snapshot = read_snapshot(directory)

    current = fingerprint(directory)
    with connect() as conn:
        if args.command == "seed" and args.if_changed and loaded_fingerprint(conn) == current:
            log.info("database already holds this snapshot; skipping seed")
            return
        load(conn, snapshot, current)


if __name__ == "__main__":
    main()
