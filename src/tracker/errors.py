"""Errors the API turns into responses. Each type carries its HTTP status and a stable code that
clients can match on; the message is for humans.

    {"error": {"code": "NOT_FOUND", "message": "TSLA is not in the coverage universe", "request_id": "..."}}
"""


class AppError(Exception):
    status = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.headers = headers or {}


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class InvalidInput(AppError):
    status = 422
    code = "VALIDATION_ERROR"


class LLMRateLimited(AppError):
    """The LLM provider is throttling us. Passed on as a 429 with its Retry-After, if it sent one."""

    status = 429
    code = "LLM_RATE_LIMITED"

    def __init__(self, message: str, retry_after: str | None = None) -> None:
        super().__init__(message, {"Retry-After": retry_after} if retry_after else None)


class LLMUnavailable(AppError):
    status = 503
    code = "LLM_UNAVAILABLE"


class LLMTimeout(AppError):
    """The question used up its time budget (ASK_TIMEOUT_SECONDS) before the model answered."""

    status = 504
    code = "LLM_TIMEOUT"


class TooManyQuestions(AppError):
    """Every /ask slot (ASK_CONCURRENCY) is busy. Refused at once rather than queued."""

    status = 429
    code = "TOO_MANY_QUESTIONS"

    def __init__(self, message: str) -> None:
        super().__init__(message, {"Retry-After": "5"})
