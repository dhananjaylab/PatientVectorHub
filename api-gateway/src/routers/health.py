"""Health check routes — K8s liveness (/health) and readiness (/ready)."""
import time
import logging

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)
router = APIRouter()
_start = time.time()


@router.get("/health", tags=["Health"])
async def liveness() -> dict:
    """Liveness probe — is the process alive?"""
    return {
        "status":   "alive",
        "uptime_s": round(time.time() - _start),
        "service":  "pvh-api-gateway",
    }


@router.get("/ready", tags=["Health"])
async def readiness(request: Request) -> JSONResponse:
    """Readiness probe — can we serve traffic?"""
    checks: dict[str, str] = {}

    # Safely resolve app state — may be None when called outside a running server
    app_state = getattr(getattr(request, "app", None), "state", None)

    # 1. PostgreSQL
    try:
        pool = getattr(app_state, "db_pool", None)
        if pool:
            await pool.fetchval("SELECT 1")
            checks["postgres"] = "ok"
        else:
            checks["postgres"] = "not_initialized"
    except Exception as e:
        checks["postgres"] = f"FAIL: {e}"
        log.warning("Readiness: postgres check failed: %s", e)

    # 2. Vault
    try:
        vault = getattr(app_state, "vault", None)
        if vault:
            vault.sys.read_health_status()
            checks["vault"] = "ok"
        else:
            checks["vault"] = "not_initialized"
    except Exception as e:
        checks["vault"] = f"FAIL: {e}"
        log.warning("Readiness: vault check failed: %s", e)

    # 3. Kafka producer
    kafka = getattr(app_state, "kafka", None)
    checks["kafka"] = "ok" if kafka else "not_initialized"

    # Ready when postgres is ok OR not yet initialized (Phase 1)
    postgres_val   = checks.get("postgres", "")
    critical_ok    = postgres_val in ("ok", "not_initialized")
    all_initialized = all(v == "ok" for v in checks.values())

    return JSONResponse(
        {
            "status": "ready" if critical_ok else "not_ready",
            "checks": checks,
        },
        status_code=200 if critical_ok else 503,
    )
