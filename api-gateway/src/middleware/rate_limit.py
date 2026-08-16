"""
PatientVectorHub — in-process rate limiting (Phase 8 / ADR-015).

Confirmed decision over Kong Gateway OSS: Kong needs its own Postgres/
Cassandra + Redis + a monitored data-plane cluster to run for real, which
cuts directly against ADR-009's pivot away from self-hosted infra (EKS,
Strimzi, CloudNativePG all got replaced by managed equivalents; nothing
in this repo's actual docker-compose.yml or CI ever stood Kong up — it
only ever existed in the aspirational doc 07-12 design). slowapi + this
service's already-running Redis (REDIS_URL — already shared by Celery's
broker/result-backend) needs zero new infrastructure.

Verified against the installed library (slowapi 0.1.10, wrapping the
`limits` package), not just its docs — two things that would otherwise
have silently broken every decorated route:

1. `@limiter.limit(...)` requires the decorated endpoint to declare BOTH
   `request: Request` AND `response: Response` as explicit parameters —
   not just `request`. When `response` is missing, the decorator's
   header-injection step raises at request time
   ("`response` must be an instance of starlette.responses.Response")
   the moment the endpoint returns anything that isn't itself a raw
   Response object — which is every route in this codebase (they all
   return Pydantic models or plain dicts). `response: Response` is a
   standard FastAPI-injectable parameter; you never touch it directly,
   slowapi mutates its headers and FastAPI merges them onto the real
   rendered response.

2. `Response.headers` (Starlette's `Headers`/`MutableHeaders`) is
   case-insensitive, but `dict(response.headers)` is not — reading
   "Retry-After" (capitalized) off a plain dict built from
   `dict(response.headers)` silently returns None even when the header
   is genuinely set as "retry-after". The custom handler below reads
   directly off the `Headers` object, not a dict copy, to avoid this.

3. `@limiter.limit(...)`'s bucket key incorporates the decorated
   function's bare `__name__` plus its `__module__`
   (`f"{view_func.__module__}.{view_func.__name__}"`, confirmed by
   reading extension.py directly, not inferred), NOT the registered
   route path. Two different routes in the SAME module that happened to
   share a Python function name would silently share one rate-limit
   bucket — one route's traffic would count against the other's limit.
   Every route decorated with @limiter.limit(...) in this codebase
   already has a distinct function name within its own module
   (ingest.py: create_job/get_job/list_jobs; query.py: rag_query;
   admin.py: create_key/revoke_key/list_keys/get_users/get_namespaces;
   audit.py: get_audit_logs/export_audit_logs), so this doesn't affect
   current behavior — but don't reuse a route handler's function name
   elsewhere in the same module if it's ever going to carry this
   decorator; reproduced the collision directly while building this
   phase's test suite (see tests/unit/test_rate_limit.py's docstring).

Decorator-per-route over a blanket ASGI middleware / global
default_limits: matches every other cross-cutting guard in this codebase
(require_role / require_min_role / get_db) being declared explicitly on
the route that needs it, not applied implicitly. Anything NOT decorated
here is simply unlimited — matching doc 09's API contract table, which
marks unlisted/health endpoints as "—" rather than assuming some global
default rate.

Fail-open, not fail-closed, on backend trouble — deliberately the
opposite of this codebase's RLS/API-key posture (ADR-010's whole point
is that auth fails closed). Rate limiting is availability-protecting,
not access-controlling: an outage in the limiter's own Redis backend
should degrade to "less protected" (per-instance in-memory counting via
in_memory_fallback_enabled) rather than "API down." This mirrors the
original doc 11 KongPlugin rate-limit config's own
`fault_tolerant: true # pass traffic if Redis unreachable` — same
intent, different mechanism. Verified concretely: pointing storage_uri
at an unreachable Redis with swallow_errors=True and
in_memory_fallback_enabled=True still enforces the configured limit
(via the in-memory fallback), rather than either raising or silently
disabling enforcement — the safer of the two failure modes.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse, Response

from ..config import settings


def rate_limit_key(request: Request) -> str:
    """Key rate-limit buckets by caller identity, not raw client IP.

    Raw-IP keying is wrong for a multi-tenant API sitting behind normal
    corporate NAT/proxy setups: many distinct users — potentially many
    distinct tenants — can share one observed IP, so IP-keying either
    under-limits a shared-IP abuser (their quota is shared with innocent
    neighbors, diluting the limit) or over-limits innocent users sharing
    an IP with someone else's heavy usage. Keying on the identity
    KeycloakJWTMiddleware already resolved (api_key_id, else
    tenant_id+user_id) makes each caller's quota their own regardless of
    network topology.

    Falls back to remote address only when no auth context exists at all
    — i.e. AUTH_ENABLED=false (local dev default) or a request that
    reached this far without credentials. Never raises: this is read via
    getattr with defaults precisely so a route decorated with
    @limiter.limit(...) can never 500 just because auth middleware
    wasn't mounted.
    """
    api_key_id = getattr(request.state, "api_key_id", None)
    if api_key_id:
        return f"apikey:{api_key_id}"
    tenant_id = getattr(request.state, "tenant_id", None)
    user_id = getattr(request.state, "user_id", None)
    if tenant_id and user_id:
        return f"user:{tenant_id}:{user_id}"
    return f"ip:{get_remote_address(request)}"


# Module-level singleton — every router imports this same instance so
# `@limiter.limit(...)` decorators across routers/ingest.py, query.py,
# audit.py, and admin.py all share one bucket store. Reuses REDIS_URL
# (already shared by Celery's broker + result backend — see
# ingestion/src/workers/celery_app.py) rather than adding a second Redis
# setting; the `limits` library's own key prefixing keeps rate-limit
# counters from colliding with Celery's keys in the same Redis instance.
#
# storage_uri connection is lazy (verified: constructing Limiter() with
# an unreachable Redis does not raise or block at construction time —
# only the first actual check touches the network), matching every other
# lazily-constructed client in this codebase (OpenAI, Anthropic, Vault).
limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri=settings.REDIS_URL,
    headers_enabled=True,
    swallow_errors=True,
    in_memory_fallback_enabled=True,
    enabled=settings.RATE_LIMIT_ENABLED,
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 handler — matches this codebase's established error
    envelope ({"error": {"code", "message", ...}}, per doc 09's example
    envelope and errors.py's PVHError-derived shape) instead of
    slowapi's own default plain-text 429 body.

    Builds a throwaway Response, lets the library's own (private but
    stable — it's what _rate_limit_exceeded_handler itself calls)
    _inject_headers() populate the standard X-RateLimit-*/Retry-After
    headers on it exactly as it would on a real response, then reads
    those headers back — case-insensitively, via the Headers object
    directly, not a plain dict copy (see module docstring point 2) — to
    populate retry_after_seconds and to forward the same headers onto
    the real JSON error response.
    """
    limiter_instance: Limiter = request.app.state.limiter
    probe = Response()
    view_limit = getattr(request.state, "view_rate_limit", None)
    if view_limit is not None:
        probe = limiter_instance._inject_headers(probe, view_limit)

    retry_after_raw = probe.headers.get("retry-after")
    body = {
        "error": {
            "code": "RATE_LIMIT_EXCEEDED",
            "message": f"Rate limit exceeded: {exc.detail}",
            "request_id": getattr(request.state, "request_id", None),
            "retry_after_seconds": (
                int(retry_after_raw) if retry_after_raw and retry_after_raw.isdigit() else None
            ),
        }
    }
    response = JSONResponse(body, status_code=429)
    for key, value in probe.headers.items():
        response.headers[key] = value
    return response
