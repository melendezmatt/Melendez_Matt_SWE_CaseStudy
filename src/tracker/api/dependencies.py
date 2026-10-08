"""Shared dependencies: the database pool, a connection per request, the LLM client, and the
limit on questions in flight.

Routes declare what they need with the Annotated aliases at the bottom; tests replace any of
them with `app.dependency_overrides`.
"""

import threading
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Path, Request
from psycopg_pool import ConnectionPool

from tracker.agent import ChatModel
from tracker.db import DbConnection
from tracker.errors import LLMUnavailable, TooManyQuestions


def get_pool(request: Request) -> ConnectionPool:
    pool: ConnectionPool = request.app.state.pool
    return pool


def get_connection(pool: Annotated[ConnectionPool, Depends(get_pool)]) -> Iterator[DbConnection]:
    """One pooled connection for the request, returned to the pool when the response is sent."""
    with pool.connection() as conn:
        yield conn


def get_model(request: Request) -> ChatModel:
    model: ChatModel | None = request.app.state.model
    if model is None:
        raise LLMUnavailable("LLM_API_KEY is not set, so /ask is off. The data endpoints still work.")
    return model


def ask_slot(request: Request) -> Iterator[None]:
    """Hold one of the ASK_CONCURRENCY slots while a question is answered. When all are taken the
    request is refused straight away (429), so questions waiting on the LLM can never occupy every
    worker thread and stall the data endpoints and /health."""
    slots: threading.BoundedSemaphore = request.app.state.ask_slots
    if not slots.acquire(blocking=False):
        raise TooManyQuestions("too many questions are being answered right now; try again shortly")
    try:
        yield
    finally:
        slots.release()


Pool = Annotated[ConnectionPool, Depends(get_pool)]
Connection = Annotated[DbConnection, Depends(get_connection)]
Model = Annotated[ChatModel, Depends(get_model)]
Ticker = Annotated[
    str,
    Path(pattern=r"^[A-Za-z][A-Za-z.\-]{0,9}$", description="Stock ticker, any case", examples=["NVDA"]),
]
