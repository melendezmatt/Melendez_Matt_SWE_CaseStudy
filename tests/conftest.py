import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from tracker.config import get_settings
from tracker.ingest import fingerprint, load, read_snapshot

sys.path.insert(0, str(Path(__file__).parent))  # so tests can `from fakes import ...`


@pytest.fixture(scope="session")
def conn() -> Iterator[psycopg.Connection]:
    """A Postgres connection loaded with the committed snapshot. Tests that need it are skipped
    when no database is reachable (e.g. running pytest outside Docker)."""
    try:
        connection = psycopg.connect(get_settings().database_url, row_factory=dict_row, connect_timeout=5)
    except psycopg.OperationalError:
        pytest.skip("no Postgres at DATABASE_URL")
    # Record the fingerprint too, so the database is left exactly as `seed` leaves it and the
    # next `docker compose up` doesn't reload a snapshot it already holds.
    snapshot_dir = get_settings().snapshot_dir
    load(connection, read_snapshot(snapshot_dir), fingerprint(snapshot_dir))
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def app(conn: psycopg.Connection) -> Iterator[FastAPI]:
    from tracker.api import create_app

    application = create_app()
    with TestClient(application):  # runs the lifespan: pool, LLM client, schema
        yield application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client per test. Dependency overrides a test sets are cleared afterwards."""
    yield TestClient(app)
    app.dependency_overrides.clear()
