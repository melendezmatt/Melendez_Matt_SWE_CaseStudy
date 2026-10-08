"""One JSON shape for every error response, and the handlers that produce it.

    {"error": {"code": "NOT_FOUND", "message": "...", "request_id": "..."}}

The error types and their status codes are defined in tracker/errors.py. `error_responses()`
documents the shape in the OpenAPI spec, so /docs and generated clients know it.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from tracker.errors import AppError

log = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


DESCRIPTIONS = {
    404: "Unknown ticker, or not enough data",
    422: "Invalid input",
    429: "Too many questions in flight, or the LLM provider is rate-limiting; see Retry-After",
    503: "The LLM is not configured or not reachable",
    504: "No answer within the time budget",
}


def error_responses(*statuses: int) -> dict[int | str, dict]:
    """The `responses=` entry for a route or router that can fail with these statuses."""
    return {status: {"model": ErrorResponse, "description": DESCRIPTIONS[status]} for status in statuses}


def error_response(
    request: Request, status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    detail = ErrorDetail(code=code, message=message, request_id=getattr(request.state, "request_id", None))
    return JSONResponse(ErrorResponse(error=detail).model_dump(), status_code=status, headers=headers)


async def app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, str(exc), exc.headers)


async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    return error_response(request, 422, "VALIDATION_ERROR", problems)


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    # Unknown routes and wrong methods, in our shape instead of Starlette's default.
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
    return error_response(request, exc.status_code, code, str(exc.detail), dict(exc.headers or {}))


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return error_response(request, 500, "INTERNAL_ERROR", "Something went wrong on our side.")


def register(app: FastAPI) -> None:
    # Starlette picks the most specific handler for each exception, so the order doesn't matter.
    app.exception_handler(AppError)(app_error)
    app.exception_handler(RequestValidationError)(invalid_request)
    app.exception_handler(HTTPException)(http_error)
    app.exception_handler(Exception)(unexpected_error)
