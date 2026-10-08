"""Postgres connections. The API shares a small pool; scripts open a single connection."""

from importlib.resources import files
from typing import Any

import psycopg
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

from tracker.config import get_settings

# A connection with any row factory. Queries choose their own row type (see service.fetch).
DbConnection = psycopg.Connection[Any]


def connect() -> psycopg.Connection[DictRow]:
    return psycopg.connect(get_settings().database_url, row_factory=dict_row)


def make_pool() -> ConnectionPool:
    return ConnectionPool(get_settings().database_url, kwargs={"row_factory": dict_row}, open=True)


def apply_schema(conn: DbConnection) -> None:
    conn.execute(files("tracker").joinpath("schema.sql").read_text())
