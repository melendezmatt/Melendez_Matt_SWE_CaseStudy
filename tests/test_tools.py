"""Tool output the model sees, with the service layer stubbed: no database."""

import pytest

from tracker import service, tools
from tracker.models import FilingRef, RiskFactorChanges


@pytest.fixture
def changes(monkeypatch: pytest.MonkeyPatch) -> None:
    result = RiskFactorChanges(
        ticker="NVDA",
        latest=FilingRef(fiscal_year=2026, url="u"),
        prior=FilingRef(fiscal_year=2025, url="u"),
        new=[f"new {i}" for i in range(31)],
        changed=[f"changed {i}" for i in range(3)],
        removed=[],
    )
    monkeypatch.setattr(service, "risk_factor_changes", lambda conn, ticker: result)


@pytest.mark.usefixtures("changes")
def test_a_cut_off_risk_factor_list_says_so_and_gives_totals() -> None:
    out = tools.risk_factor_changes(None, [], "NVDA")  # type: ignore[arg-type]
    assert out["totals"] == {"new": 31, "changed": 3, "removed": 0}
    assert out["truncated"] is True and len(out["new_paragraphs"]) == 20
    assert "Only part" in out["note"]


@pytest.mark.usefixtures("changes")
def test_the_rest_of_the_list_is_one_call_away() -> None:
    out = tools.risk_factor_changes(None, [], "NVDA", offset=20)  # type: ignore[arg-type]
    assert out["new_paragraphs"] == [f"new {i}" for i in range(20, 31)]
    assert out["truncated"] is False and out["note"] == "These are all the changes found."
