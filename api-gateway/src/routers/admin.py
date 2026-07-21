"""
PatientVectorHub — admin routes (API keys, users).

This is the first real protected router wired into main.py. It exists in
this pass mainly as a concrete, testable proof that the Phase 2 (DB) and
Phase 3 (Auth/RBAC) work fit together correctly end to end — create_key()
touches db.crud (Phase 2), require_role("admin") touches middleware.rbac
(Phase 3), and get_current_user()/get_db() touch deps.py, which reads the
request.state that middleware.auth.KeycloakJWTMiddleware populates.

The full admin surface (namespace health, settings, etc.) is Phase 8+
territory per the original doc 06 implementation plan; this router only
covers what api_keys/users CRUD in this pass already supports.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db import crud
from ..deps import get_current_user, get_db
from ..middleware.rbac import require_role
from ..schemas.admin import (
    ApiKeyListResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    UserListResponse,
)

router = APIRouter()


@router.post(
    "/api-keys",
    response_model=CreateApiKeyResponse,
    status_code=201,
    dependencies=[require_role("admin")],
)
async def create_key(
    body: CreateApiKeyRequest,
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
async def revoke_key(key_id: str, db=Depends(get_db), user=Depends(get_current_user)) -> None:
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
async def list_keys(db=Depends(get_db)) -> ApiKeyListResponse:
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
async def get_users(db=Depends(get_db)) -> UserListResponse:
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
