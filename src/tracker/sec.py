"""SEC EDGAR client: company facts (XBRL), filing history, and filing documents."""

import time

import httpx

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
DOCUMENT_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{document}"

# SEC allows 10 requests a second; pausing between requests keeps us well under that.
PAUSE_SECONDS = 0.2


def document_url(cik: int, accession: str, document: str) -> str:
    return DOCUMENT_URL.format(cik=cik, folder=accession.replace("-", ""), document=document)


class SecClient:
    def __init__(self, user_agent: str) -> None:
        self._http = httpx.Client(headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)

    def _get(self, url: str) -> httpx.Response:
        time.sleep(PAUSE_SECONDS)
        response = self._http.get(url)
        response.raise_for_status()
        return response

    def ticker_to_cik(self) -> dict[str, tuple[int, str]]:
        """Every SEC-registered ticker -> (CIK, company name)."""
        rows = self._get(TICKERS_URL).json().values()
        return {r["ticker"].upper(): (int(r["cik_str"]), r["title"]) for r in rows}

    def company_facts(self, cik: int) -> dict:
        return self._get(COMPANY_FACTS_URL.format(cik=cik)).json()

    def submissions(self, cik: int) -> dict:
        return self._get(SUBMISSIONS_URL.format(cik=cik)).json()

    def document(self, cik: int, accession: str, document: str) -> str:
        return self._get(document_url(cik, accession, document)).text

    def close(self) -> None:
        self._http.close()
