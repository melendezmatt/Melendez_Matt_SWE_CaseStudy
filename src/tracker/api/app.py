"""The FastAPI application: lifespan (shared resources), middleware, error handlers, routers."""

import threading
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from tracker import agent
from tracker.api import companies, errors, operations, questions, rankings
from tracker.config import get_settings
from tracker.db import apply_schema, make_pool


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create what every request shares once, at startup, and release it at shutdown."""
    settings = get_settings()
    app.state.pool = make_pool()
    app.state.model = agent.model_from_settings(settings)
    app.state.ask_slots = threading.BoundedSemaphore(settings.ask_concurrency)
    with app.state.pool.connection() as conn:
        apply_schema(conn)
    yield
    app.state.pool.close()


async def request_id(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Tag every request with an ID (the caller's X-Request-ID, or a new one). It's returned in a
    header and in error bodies, so a user's report can be matched to the server logs."""
    request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Fundamentals Tracker",
        description="SEC fundamentals, 10-K text and market prices, with a Q&A agent on top.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.middleware("http")(request_id)
    errors.register(app)
    for module in (companies, rankings, questions, operations):
        app.include_router(module.router)
    return app
