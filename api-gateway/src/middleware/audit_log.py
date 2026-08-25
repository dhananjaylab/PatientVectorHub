"""
PatientVectorHub — audit-log middleware (Phase 10 / ADR-017).

This is the file main.py's own placeholder comment names:
    # Phase 10 (Security): AuditLogMiddleware uncomment when ready
    # from .middleware.audit_log import AuditLogMiddleware

Two distinct jobs, not one:

1. Populate request.state.ip_address before the request reaches any
   router. db/crud.write_audit_log() has accepted an `ip_address`
   parameter since migration 004, but every existing call site
   (routers/admin.py, ingest.py, query.py, audit.py) only ever passes
   `action`/`user_id`/`metadata` -- the column has been silently NULL
   since Phase 8. This middleware doesn't populate it FOR those callers
   (they still call write_audit_log() themselves, with their own
   already-open tenant-scoped session); it just makes
   request.state.ip_address available for them to pass along. See this
   phase's router diffs for the actual call-site updates.

2. Record 'access_denied' audit rows for 403 responses (RBAC denial)
   that no router-level code would otherwise ever log -- a rejected
   require_role()/require_min_role() check raises HTTPException(403)
   straight out of middleware/rbac.py, well before any router's own
   write_audit_log() call would run.

Deliberately does NOT attempt to log bare 401s (authentication failure
with no credential resolved at all) to audit_logs. audit_logs is FORCE
RLS'd and every row's tenant_id comes from current_setting
('app.tenant_id') inside an already-tenant-scoped session
(db/session.py's get_tenant_session()) -- a request that never
established WHO it was has no tenant to scope a row to. Attempting a
write there wouldn't just be semantically odd, it would violate RLS
outright (INSERT ... WITH CHECK evaluates false against a NULL
tenant_id) and raise, which would then have to be swallowed to avoid
turning an audit side-effect into a 500 for the caller -- worse than
just not attempting it. A bare 401's trail lives in the structured JSON
access logs (logging_config.py) instead, which need no tenant context.
403s are different: by the time RBAC rejects a request, authentication
already succeeded (request.state.tenant_id IS populated), so a real,
correctly-scoped row can be written.

Positioned OUTERMOST in main.py's middleware stack (added last -- see
that file's own "last added = first executed" comment), which was a
genuine, not cosmetic, reordering: request_id_middleware previously sat
*inside* (added before) KeycloakJWTMiddleware, so a 401 short-circuit
never got its X-Request-ID header set at all before this phase. Moving
request_id_middleware outward (still inside this middleware, which is
outermost of all) fixes that as a side effect of giving this middleware
a reliable request_id to attach to every access_denied row -- see
main.py's own reordering comment for the verification.
"""
from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

log = logging.getLogger(__name__)

_DENIED_STATUS_CODES = frozenset({403})


class AuditLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.ip_address = request.client.host if request.client else None

        response = await call_next(request)

        if response.status_code in _DENIED_STATUS_CODES:
            await self._record_access_denied(request, response.status_code)

        return response

    @staticmethod
    async def _record_access_denied(request: Request, status_code: int) -> None:
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            # No authenticated tenant context -- see module docstring for
            # why this deliberately does not attempt an audit_logs write.
            log.info(
                "access_denied (no tenant context, not written to audit_logs)",
                extra={
                    "path": request.url.path,
                    "status_code": status_code,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )
            return

        # Imported here, not at module scope, matching
        # middleware/auth.py's own precedent for _authenticate_api_key:
        # keeps this middleware's import graph light for the (fairly
        # common) request that never trips a 403 at all.
        from ..db import crud
        from ..db.session import get_tenant_session

        try:
            async with get_tenant_session(str(tenant_id)) as db:
                await crud.write_audit_log(
                    db,
                    action="access_denied",
                    user_id=getattr(request.state, "user_id", None),
                    api_key_id=getattr(request.state, "api_key_id", None),
                    ip_address=getattr(request.state, "ip_address", None),
                    request_id=getattr(request.state, "request_id", None),
                    status_code=status_code,
                    metadata={
                        "path": request.url.path,
                        "method": request.method,
                        "role": getattr(request.state, "role", None),
                    },
                )
        except Exception as e:  # noqa: BLE001
            # An audit-logging failure must never turn into a 500 for a
            # request that was already correctly rejected with 403 --
            # the response has already been built and is on its way
            # out. Log loudly so this is never silently invisible.
            log.error(
                "Failed to write access_denied audit row: %s",
                e,
                extra={"path": request.url.path, "tenant_id": str(tenant_id)},
            )
