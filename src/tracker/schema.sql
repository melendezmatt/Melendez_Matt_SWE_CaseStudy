-- Applied on every start; every statement is idempotent.

CREATE TABLE IF NOT EXISTS companies (
    ticker  TEXT PRIMARY KEY,
    cik     INTEGER NOT NULL UNIQUE,
    name    TEXT NOT NULL
);

-- One row per company, metric and fiscal year ("long" format), so adding a metric is a line in
-- xbrl.py rather than a migration. `concept` and `accession` record where each number came from.
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker       TEXT NOT NULL REFERENCES companies ON DELETE CASCADE,
    metric       TEXT NOT NULL,
    fiscal_year  INTEGER NOT NULL,
    period_end   DATE NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    concept      TEXT NOT NULL,     -- XBRL tag, e.g. "us-gaap:Revenues", or "derived: <formula>"
    accession    TEXT NOT NULL,     -- the SEC filing the value was taken from
    PRIMARY KEY (ticker, metric, period_end),
    CHECK (fiscal_year = EXTRACT(YEAR FROM period_end))
);

CREATE TABLE IF NOT EXISTS prices (
    ticker  TEXT NOT NULL REFERENCES companies ON DELETE CASCADE,
    date    DATE NOT NULL,
    close   DOUBLE PRECISION NOT NULL CHECK (close > 0),  -- split-adjusted, like SEC's restated EPS
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS filings (
    accession    TEXT PRIMARY KEY,
    ticker       TEXT NOT NULL REFERENCES companies ON DELETE CASCADE,
    filed        DATE NOT NULL,
    period_end   DATE NOT NULL,     -- the fiscal year end the 10-K reports on
    fiscal_year  INTEGER,
    url          TEXT NOT NULL,
    CHECK (filed > period_end)
);

-- Full text of Item 1A and Item 7, kept whole for the year-over-year comparison.
CREATE TABLE IF NOT EXISTS filing_sections (
    accession  TEXT NOT NULL REFERENCES filings ON DELETE CASCADE,
    section    TEXT NOT NULL CHECK (section IN ('risk_factors', 'mdna')),
    text       TEXT NOT NULL,
    PRIMARY KEY (accession, section)
);

-- The same text in ~1,500-character chunks for search. Postgres full-text search keeps
-- everything in one database and needs no embedding model.
CREATE TABLE IF NOT EXISTS filing_chunks (
    accession  TEXT NOT NULL,
    section    TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    text       TEXT NOT NULL,
    tsv        TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    PRIMARY KEY (accession, section, seq),
    FOREIGN KEY (accession, section) REFERENCES filing_sections ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS filing_chunks_tsv_idx ON filing_chunks USING GIN (tsv);

-- Which snapshot the database holds (one row), so `seed --if-changed` reloads only a new one.
CREATE TABLE IF NOT EXISTS snapshot_loaded (
    only_row     BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (only_row),
    fingerprint  TEXT NOT NULL,     -- sha256 of the snapshot files
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
