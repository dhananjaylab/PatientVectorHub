"""PVH custom exception hierarchy + FastAPI exception handler.

RECONSTRUCTED (Phase 10 prep): this file came through as "[Binary file]"
(unreadable) in the repo dump used to seed Phase 10 work -- the exact
same failure mode ingestion/requirements.txt's own docstring already
documents happening once before for that file. The public contract here
is reconstructed with high confidence from tests/unit/test_errors.py
(which enumerates every class, status_code, and error_code exactly) plus
the two real call sites (routers/query.py's QueryError/LLMError usage,
main.py's single `add_exception_handler(PVHError, pvh_exception_handler)`
registration) and middleware/rate_limit.py's error envelope shape
({"error": {"code", "message", "request_id"}}), which this mirrors for
consistency. Please diff against your real errors.py and reconcile --
flagging this the same way doc 4's ingestion/requirements.txt precedent
did, rather than silently presenting a guess as ground truth.
"""
from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class PVHError(Exception):
    """Base for every PVH-specific exception. main.py registers exactly
    one handler for this base class, so every subclass below is handled
    without its own registration line."""

    status_code: int = 500
    error_code: str = "PVH_ERROR"

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class AuthenticationError(PVHError):
    status_code = 401
    error_code = "AUTHENTICATION_FAILED"


class AuthorizationError(PVHError):
    status_code = 403
    error_code = "AUTHORIZATION_FAILED"


class NotFoundError(PVHError):
    status_code = 404
    error_code = "NOT_FOUND"


class TenantMismatchError(PVHError):
    status_code = 403
    error_code = "TENANT_MISMATCH"


class IngestionError(PVHError):
    status_code = 500
    error_code = "INGESTION_ERROR"


class EmbeddingError(IngestionError):
    """Deliberately keeps IngestionError's 500 status_code (untested,
    unconstrained) but gets its own error_code so
    TestErrorCodeUniqueness.test_all_error_codes_unique still passes."""

    error_code = "EMBEDDING_ERROR"


class VectorStoreError(PVHError):
    status_code = 503
    error_code = "VECTOR_STORE_ERROR"


class QueryError(PVHError):
    status_code = 500
    error_code = "QUERY_ERROR"


class LLMError(PVHError):
    status_code = 503
    error_code = "LLM_ERROR"


async def pvh_exception_handler(request: Request, exc: PVHError) -> JSONResponse:
    """Same {"error": {...}} envelope as
    middleware/rate_limit.py's rate_limit_exceeded_handler, so API
    consumers see one consistent error shape regardless of which
    handler caught the failure."""
    log.warning(
        "%s: %s",
        exc.error_code,
        exc.message,
        extra={"detail": exc.detail, "path": request.url.path},
    )
    body: dict = {
        "error": {
            "code": exc.error_code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", None),
        }
    }
    if exc.detail:
        body["error"]["detail"] = exc.detail
    return JSONResponse(body, status_code=exc.status_code)
