"""/rankings: every company ranked on one metric."""

from fastapi import APIRouter

from tracker import service
from tracker.api.dependencies import Connection
from tracker.api.errors import error_responses
from tracker.metrics import Metric
from tracker.models import RankingRow

router = APIRouter(prefix="/rankings", tags=["rankings"], responses=error_responses(422))


@router.get("/{metric}")
def get_ranking(conn: Connection, metric: Metric, fiscal_year: int | None = None) -> list[RankingRow]:
    """Highest first. Without fiscal_year, each company's latest fiscal year is used; check
    period_end, since fiscal years end on different dates."""
    return service.ranking(conn, metric, fiscal_year)
