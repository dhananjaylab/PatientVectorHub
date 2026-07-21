"""
PatientVectorHub — role-based access control guards.

FastAPI dependencies that read request.state.role (set by either
KeycloakJWTMiddleware for JWT requests, or deps.get_current_user() for
resolved API-key requests) and enforce a minimum role or an exact allow-
list. Anonymous requests default to "readonly" via getattr's fallback, so
an unauthenticated caller is treated as the lowest-privilege role rather
than raising an AttributeError.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from starlette.requests import Request

# Higher value = more permissions. Kept identical to auth.py's
# _ROLE_PRIORITY ordering and to infra/keycloak/realm.json's realm roles.
_HIERARCHY = {"admin": 4, "engineer": 3, "analyst": 2, "auditor": 1, "readonly": 0}


def require_role(*allowed_roles: str):
    """FastAPI Depends — only an exact role in allowed_roles passes.

    Usage: @router.post(..., dependencies=[require_role("admin")])
    """

    def check(request: Request) -> str:
        role = getattr(request.state, "role", "readonly")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=403, detail=f"Role {role!r} not in {allowed_roles}"
            )
        return role

    return Depends(check)


def require_min_role(min_role: str):
    """FastAPI Depends — role must be >= min_role in the hierarchy.

    Usage: @router.get(..., dependencies=[require_min_role("analyst")])
    """
    min_level = _HIERARCHY.get(min_role, 0)

    def check(request: Request) -> str:
        role = getattr(request.state, "role", "readonly")
        level = _HIERARCHY.get(role, -1)
        if level < min_level:
            raise HTTPException(
                status_code=403, detail=f"Role {role!r} insufficient — need {min_role!r}+"
            )
        return role

    return Depends(check)
