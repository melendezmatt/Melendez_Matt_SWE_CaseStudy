"""/rankings: every company ranked on one metric."""

from typing import Annotated

from fastapi import APIRouter, Query

from tracker import service
from tracker.api.dependencies import Connection
from tracker.api.errors import error_responses
from tracker.metrics import Metric
from tracker.models import RankingRow

router = APIRouter(prefix="/rankings", tags=["rankings"], responses=error_responses(422))


@router.get("/{metric}")
def get_ranking(
    conn: Connection,
    metric: Metric,
    fiscal_year: Annotated[int | None, Query(description="Compare fiscal years with this label")] = None,
    calendar_year: Annotated[
        int | None,
        Query(description="Compare the fiscal years that fall mostly in this calendar year"),
    ] = None,
) -> list[RankingRow]:
    """Highest first. By default each company's latest fiscal year is used; check period_end, since
    fiscal years end on different dates. Labels can mislead: NVDA's FY2025 ended in January 2025,
    ETN's in December 2025. calendar_year lines the years up by when they mostly happened."""
    return service.ranking(conn, metric, fiscal_year, calendar_year)
