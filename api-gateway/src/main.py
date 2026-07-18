"""
PatientVectorHub — API Gateway
FastAPI application factory.

Phase 1: health endpoints, structured logging, exception handling.
Phase 2: DB session, models, CRUD, dependency injection.
Phase 3: Keycloak JWT middleware, RBAC.
"""
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .errors import PVHError, pvh_exception_handler
from .logging_config import configure_logging
from .routers.health import router as health_router

configure_logging(settings.LOG_LEVEL)

import logging
log = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting PatientVectorHub API Gateway",
             extra={"environment": settings.ENVIRONMENT, "version": "1.0.0"})

    # Phase 1 stubs — replaced in later phases
    app.state.db_pool = None   # Phase 2: asyncpg pool
    app.state.vault   = None   # Phase 2: hvac.Client
    app.state.kafka   = None   # Phase 4: AIOKafkaProducer

    log.info("API Gateway ready", extra={"routes": len(app.routes)})
    yield

    log.info("Shutting down...")
    if getattr(app.state, "kafka", None):
        await app.state.kafka.stop()
    if getattr(app.state, "db_pool", None):
        await app.state.db_pool.close()
    log.info("Shutdown complete")


# ── Request ID middleware ──────────────────────────────────────────────────────
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="PatientVectorHub API",
        description=(
            "HIPAA-compliant enterprise RAG platform for 1.5B patient documents. "
            "Multi-tenant, OpenID Connect secured, OpenAI-embedding powered."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(PVHError, pvh_exception_handler)  # type: ignore

    @app.exception_handler(404)
    async def not_found(request: Request, exc) -> JSONResponse:
        return JSONResponse(
            {"error": {"code": "NOT_FOUND",
                       "message": f"{request.url.path} not found"}},
            status_code=404,
        )

    @app.exception_handler(500)
    async def internal(request: Request, exc) -> JSONResponse:
        log.error("Unhandled exception", extra={"path": str(request.url)})
        return JSONResponse(
            {"error": {"code": "INTERNAL_ERROR",
                       "message": "An unexpected error occurred"}},
            status_code=500,
        )

    # ── Middleware (last added = first executed) ───────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_id_middleware)

    # Keycloak middleware is enabled once api-gateway/src/middleware/auth.py exists.
    if settings.AUTH_ENABLED:
        from .middleware.auth import KeycloakJWTMiddleware

        app.add_middleware(
            KeycloakJWTMiddleware,
            jwks_url=settings.KEYCLOAK_JWKS_URL,
            public_paths=frozenset({
                "/health", "/ready", "/docs", "/redoc",
                "/openapi.json", "/metrics",
            }),
        )

    # Phase 10 (Security): AuditLogMiddleware uncomment when ready
    # from .middleware.audit_log import AuditLogMiddleware
    # app.add_middleware(AuditLogMiddleware)

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(health_router)

    # Phase 8+ routers (uncomment as phases complete):
    # from .routers.ingest import router as ingest_router
    # from .routers.query  import router as query_router
    # from .routers.audit  import router as audit_router
    # from .routers.admin  import router as admin_router
    # app.include_router(ingest_router, prefix="/v1/ingest", tags=["Ingestion"])
    # app.include_router(query_router,  prefix="/v1/query",  tags=["Query"])
    # app.include_router(audit_router,  prefix="/v1/audit",  tags=["Audit"])
    # app.include_router(admin_router,  prefix="/v1/admin",  tags=["Admin"])

    return app


app = create_app()
