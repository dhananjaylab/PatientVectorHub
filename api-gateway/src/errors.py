"""
PatientVectorHub — custom exception hierarchy.
All application errors inherit from PVHError so FastAPI
can catch and format them uniformly as the standard error envelope.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class PVHError(Exception):
    """Base error for all PatientVectorHub exceptions."""
    status_code: int = 500
    error_code:  str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail  = detail


# ── Auth ──────────────────────────────────────────────────────────────────────
class AuthenticationError(PVHError):
    status_code = 401
    error_code  = "AUTHENTICATION_FAILED"

class AuthorizationError(PVHError):
    status_code = 403
    error_code  = "AUTHORIZATION_FAILED"


# ── Tenant ────────────────────────────────────────────────────────────────────
class TenantNotFoundError(PVHError):
    status_code = 404
    error_code  = "TENANT_NOT_FOUND"

class TenantMismatchError(PVHError):
    status_code = 403
    error_code  = "TENANT_MISMATCH"


# ── Ingestion ─────────────────────────────────────────────────────────────────
class IngestionError(PVHError):
    status_code = 422
    error_code  = "INGESTION_ERROR"

class DocumentParseError(IngestionError):
    error_code = "DOCUMENT_PARSE_ERROR"

class ChunkingError(IngestionError):
    error_code = "CHUNKING_ERROR"

class EmbeddingError(IngestionError):
    status_code = 503
    error_code  = "EMBEDDING_ERROR"


# ── Vector store ──────────────────────────────────────────────────────────────
class VectorStoreError(PVHError):
    status_code = 503
    error_code  = "VECTOR_STORE_ERROR"

class VectorStoreUnavailableError(VectorStoreError):
    error_code = "VECTOR_STORE_UNAVAILABLE"


# ── Query ─────────────────────────────────────────────────────────────────────
class QueryError(PVHError):
    status_code = 422
    error_code  = "QUERY_ERROR"

class LLMError(PVHError):
    status_code = 503
    error_code  = "LLM_ERROR"

class LLMRateLimitError(LLMError):
    status_code = 429
    error_code  = "LLM_RATE_LIMIT"


# ── Not found ─────────────────────────────────────────────────────────────────
class NotFoundError(PVHError):
    status_code = 404
    error_code  = "NOT_FOUND"


# ── FastAPI exception handler ─────────────────────────────────────────────────
async def pvh_exception_handler(request: Request, exc: PVHError) -> JSONResponse:
    """
    Converts any PVHError into the standard API error envelope.
    Registered in main.py: app.add_exception_handler(PVHError, pvh_exception_handler)
    """
    import uuid
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code":       exc.error_code,
                "message":    exc.message,
                "detail":     exc.detail,
                "request_id": request.headers.get("X-Request-ID", str(uuid.uuid4())),
            }
        },
    )
