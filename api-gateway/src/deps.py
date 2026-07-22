"""
PatientVectorHub — FastAPI dependency injection.

get_db() is the only place route handlers should obtain a DB session: it
requires request.state.tenant_id to already be set (by
middleware.auth.KeycloakJWTMiddleware, via either the JWT or X-API-Key
path) and raises 401 if it isn't, rather than silently falling back to an
untenanted session. That 401 is deliberate — with AUTH_ENABLED=false (the
local-dev default in .env.example), the middleware isn't even mounted, so
protected routes correctly refuse to serve data rather than quietly
running with no tenant context.
"""
from __future__ import annotations

from typing import AsyncIterator

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .db.session import get_tenant_session


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing tenant context")
    async with get_tenant_session(tenant_id) as session:
        yield session


async def get_current_user(request: Request) -> dict:
    return {
        "user_id": getattr(request.state, "user_id", None),
        "tenant_id": getattr(request.state, "tenant_id", None),
        "role": getattr(request.state, "role", "readonly"),
        "email": getattr(request.state, "email", None),
        "auth_method": getattr(request.state, "auth_method", None),
        "api_key_id": getattr(request.state, "api_key_id", None),
        "scopes": getattr(request.state, "scopes", []),
    }
