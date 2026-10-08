"""/health: readiness for Docker, load balancers and monitoring."""

import logging
from typing import Literal

import psycopg
from fastapi import APIRouter, Response
from psycopg_pool import PoolTimeout
from pydantic import BaseModel

from tracker.api.dependencies import Pool

log = logging.getLogger(__name__)

router = APIRouter(tags=["operations"])


class Health(BaseModel):
    status: Literal["ok", "unavailable"]


@router.get("/health", responses={503: {"model": Health, "description": "The database is unreachable"}})
def health(pool: Pool, response: Response) -> Health:
    """Healthy means the database answers, not just that the process is up."""
    try:
        with pool.connection(timeout=2) as conn:
            conn.execute("SELECT 1")
    except (psycopg.Error, PoolTimeout):
        log.exception("health check: database unreachable")
        response.status_code = 503
        return Health(status="unavailable")
    return Health(status="ok")
