"""
PatientVectorHub — admin routes (API keys, users, vector-store namespace
health).

This is the first real protected router wired into main.py (Phase 3) —
create_key() touches db.crud (Phase 2), require_role("admin") touches
middleware.rbac (Phase 3), and get_current_user()/get_db() touch deps.py,
which reads the request.state that middleware.auth.KeycloakJWTMiddleware
populates.

Phase 8 changes (ADR-015):
  - Every route gained `request: Request` + `response: Response` params
    and a `@limiter.limit(...)` decorator. Both params are required by
    slowapi's decorator (see middleware/rate_limit.py's docstring for
    why — every route here returns a Pydantic model or None, never a
    raw Response, so the decorator reads/writes headers through the
    injected `response` param instead).
  - New `GET /vector-store/namespaces` — doc 09's API contract lists
    this at "engineer+ / ingest:read / 200/min", a DIFFERENT (lower)
    bar than every other route in this file (all `require_role("admin")`
    exact-match). That's intentional, not an inconsistency to fix:
    engineers doing ingestion ops need to check vector-store health as
    routine work (doc 03's Vector Store page access level is
    "engineer+"), while API-key/user management stays admin-only. This
    file is an organizational grouping (admin-surface routes), not a
    uniform-permission boundary — RBAC is declared per-route throughout
    this codebase, never implied by which file a route lives in.

    Imports `vector_store.interface.get_store` at module level, matching
    routers/query.py's precedent from Phase 7 (ADR-014) rather than the
    local-import style an earlier, non-authoritative design sketch used
    — no new Dockerfile or sitecustomize.py wiring is needed for this:
    ADR-014 already made `vector_store` resolvable from api-gateway
    (Dockerfile COPYs vector-store/src/ in, sitecustomize.py adds it to
    sys.path for local dev, conftest.py aliases it for tests) when it
    added the identical import for rag_engine's cross-package reach into
    vector_store.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from vector_store.interface import get_store

from ..config import settings
from ..db import crud
from ..deps import get_current_user, get_db
from ..middleware.rate_limit import limiter
from ..middleware.rbac import require_min_role, require_role
from ..schemas.admin import (
    ApiKeyListResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    NamespaceHealthResponse,
    UserListResponse,
)

router = APIRouter()


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=201,
    dependencies=[require_role("admin")],
)
@limiter.limit("20/minute")  # doc 09: POST /v1/admin/api-keys — 20/min
async def create_key(
    body: CreateApiKeyRequest,
    request: Request,
    response: Response,
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> CreateApiKeyResponse:
    result = await crud.create_api_key(
        db,
        name=body.name,
        scopes=body.scopes,
        expires_days=body.expires_days,
        user_id=user["user_id"],
    )
    await crud.write_audit_log(
        db, action="api_key_create", user_id=user["user_id"], metadata={"key_id": result["key_id"]}
    )
    return CreateApiKeyResponse(**result)


@router.delete(
    "/api-keys/{key_id}",
    status_code=204,
    dependencies=[require_role("admin")],
)
@limiter.limit("20/minute")  # doc 09: DELETE /v1/admin/api-keys/{id} — 20/min
async def revoke_key(
    key_id: str,
    request: Request,
    response: Response,
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> None:
    if not await crud.revoke_api_key(db, key_id=key_id):
        raise HTTPException(status_code=404, detail="API key not found")
    await crud.write_audit_log(
        db, action="api_key_revoke", user_id=user["user_id"], metadata={"key_id": key_id}
    )


@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    dependencies=[require_role("admin")],
)
@limiter.limit("200/minute")  # not in doc 09's table; matches this file's other reads
async def list_keys(request: Request, response: Response, db=Depends(get_db)) -> ApiKeyListResponse:
    rows = await crud.list_api_keys(db)
    return ApiKeyListResponse(
        api_keys=[
            {
                **r,
                "id": str(r["id"]),
                "user_id": str(r["user_id"]),
                "expires_at": r["expires_at"].isoformat(),
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    )


@router.get("/users", response_model=UserListResponse, dependencies=[require_role("admin")])
@limiter.limit("200/minute")
async def get_users(request: Request, response: Response, db=Depends(get_db)) -> UserListResponse:
    rows = await crud.list_users(db)
    return UserListResponse(
        users=[
            {
                **r,
                "id": str(r["id"]),
                "last_login": r["last_login"].isoformat() if r["last_login"] else None,
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    )


@router.get(
    "/vector-store/namespaces",
    response_model=NamespaceHealthResponse,
    dependencies=[require_min_role("engineer")],
)
@limiter.limit("200/minute")  # doc 09: GET /v1/vector-store/namespaces — 200/min
async def get_namespaces(
    request: Request,
    response: Response,
    user=Depends(get_current_user),
) -> NamespaceHealthResponse:
    store = get_store(user["tenant_id"])
    healthy = await store.health_check()
    return NamespaceHealthResponse(
        tenant_id=user["tenant_id"],
        backend=settings.VECTOR_BACKEND,
        healthy=healthy,
    )
