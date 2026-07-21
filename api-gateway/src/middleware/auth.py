"""
PatientVectorHub — authentication context middleware.

Handles both credential types doc 09's API contracts describe:
  - Authorization: Bearer <keycloak_jwt>  (human users, OIDC/PKCE)
  - X-API-Key: <key>                      (service accounts)

Both paths populate the same request.state fields (user_id, tenant_id,
role, auth_method) so that middleware/rbac.py's require_role() /
require_min_role() work identically regardless of which credential was
used — deps.py never has to care which path authenticated the request.

Why both live in one middleware rather than JWT-in-middleware and
API-key-in-a-dependency: middleware is guaranteed to run before every
FastAPI dependency, so request.state is fully populated by the time any
RBAC guard evaluates it. Splitting auth across a middleware and a
dependency would make request.state population order depend on FastAPI's
internal dependency resolution order, which is not something a
role-enforcement check should ever rely on.

JWT verification is done with PyJWT + PyJWKClient rather than python-jose:
python-jose has had no meaningful release in years, depends on the still-
unpatched `ecdsa` package (a known timing side-channel), and FastAPI's own
docs moved off it for the same reasons. PyJWKClient's HTTP fetch is
synchronous, so it's called via run_in_threadpool to avoid blocking the
event loop.

API-key resolution (db.crud.resolve_api_key) calls a SECURITY DEFINER
Postgres function that only actually bypasses RLS once its owning role has
been separately granted BYPASSRLS by a DB admin (see ADR-010). Until that
grant exists in an environment, every X-API-Key request gets a generic 401
here — fail-closed, not fail-open, and indistinguishable from "this key
doesn't exist" by design (an environment-provisioning gap should never be
observable to an external caller as anything other than "unauthenticated").

Scopes stored on api_keys (e.g. ['ingest:write', 'query:read']) are mapped
to a single effective `role` so the existing role-hierarchy RBAC guards
work uniformly for both credential types. The raw scopes list is still
attached to request.state.scopes for any future per-scope enforcement;
doc 09 treats role (JWT) and scope (API key) as parallel authorization
axes, and collapsing them here is a deliberate Phase 3 simplification, not
an oversight — split them back out if/when a route needs true per-scope
checks independent of role.

Only wired into the app when settings.AUTH_ENABLED=true (see main.py) —
local dev defaults to AUTH_ENABLED=false so Phase 2/3 work doesn't require
a running Keycloak container to iterate.
"""
from __future__ import annotations

import logging

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

_DEFAULT_PUBLIC_PATHS = frozenset(
    {"/health", "/ready", "/docs", "/redoc", "/openapi.json", "/metrics"}
)
_ROLE_PRIORITY = ["admin", "engineer", "analyst", "auditor", "readonly"]
_JWKS_CACHE_LIFESPAN_SECONDS = 300  # matches doc 10's Flow 1 design (5 min)

# Scope -> effective role, highest-privilege match wins. Deliberately
# simplified — see module docstring.
_SCOPE_TO_ROLE = [
    ("admin:write", "admin"),
    ("ingest:write", "engineer"),
    ("query:read", "analyst"),
    ("audit:read", "auditor"),
]


class KeycloakJWTMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        jwks_url: str,
        issuer: str | None = None,
        audience: str | None = None,
        public_paths: frozenset[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.issuer = issuer
        self.audience = audience
        self.public_paths = public_paths or _DEFAULT_PUBLIC_PATHS
        self._jwks_client = PyJWKClient(
            jwks_url, cache_jwk_set=True, lifespan=_JWKS_CACHE_LIFESPAN_SECONDS
        )

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.public_paths:
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key")

        if auth_header.startswith("Bearer "):
            error = await self._authenticate_jwt(request, auth_header.removeprefix("Bearer ").strip())
            if error is not None:
                return error
        elif api_key:
            error = await self._authenticate_api_key(request, api_key)
            if error is not None:
                return error
        # else: no credential at all — pass through anonymous; RBAC guards
        # (which default missing request.state.role to "readonly") decide
        # whether that's acceptable for this route.

        return await call_next(request)

    async def _authenticate_jwt(self, request: Request, token: str) -> JSONResponse | None:
        try:
            signing_key = await run_in_threadpool(
                self._jwks_client.get_signing_key_from_jwt, token
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={"verify_aud": self.audience is not None},
            )
        except PyJWKClientError as e:
            log.error("JWKS fetch/kid lookup failed: %s", e)
            return JSONResponse(
                {
                    "error": {
                        "code": "AUTHENTICATION_UNAVAILABLE",
                        "message": "Could not reach identity provider",
                    }
                },
                status_code=503,
            )
        except PyJWTError as e:
            return JSONResponse(
                {"error": {"code": "AUTHENTICATION_FAILED", "message": str(e)}},
                status_code=401,
            )

        request.state.user_id = payload.get("sub")
        request.state.tenant_id = payload.get("tenant_id")
        request.state.email = payload.get("email")
        request.state.role = self._extract_role(payload)
        request.state.scopes = []
        request.state.auth_method = "jwt"
        return None

    async def _authenticate_api_key(self, request: Request, raw_key: str) -> JSONResponse | None:
        # Imported here (not at module scope) to avoid making this
        # middleware's import graph reach into db/config at app import
        # time for JWT-only deployments — resolve_api_key pulls in
        # SQLAlchemy + asyncpg, which is only actually needed if the
        # request carries an API key.
        from ..db.crud import resolve_api_key

        try:
            resolved = await resolve_api_key(raw_key)
        except Exception as e:  # DB unreachable, resolver function missing, etc.
            log.error("API key resolution failed: %s", e)
            return JSONResponse(
                {
                    "error": {
                        "code": "AUTHENTICATION_UNAVAILABLE",
                        "message": "Could not verify API key",
                    }
                },
                status_code=503,
            )

        if resolved is None:
            # Covers: key not found, revoked, expired, AND "BYPASSRLS not
            # yet granted in this environment" (ADR-010) — all fail closed
            # to the same generic response, deliberately indistinguishable
            # from the caller's perspective.
            return JSONResponse(
                {"error": {"code": "AUTHENTICATION_FAILED", "message": "Invalid or expired API key"}},
                status_code=401,
            )

        scopes = resolved.get("scopes") or []
        request.state.user_id = str(resolved["user_id"]) if resolved.get("user_id") else None
        request.state.tenant_id = str(resolved["tenant_id"])
        request.state.email = None
        request.state.role = self._role_from_scopes(scopes)
        request.state.scopes = scopes
        request.state.api_key_id = str(resolved["key_id"])
        request.state.auth_method = "api_key"
        return None

    @staticmethod
    def _extract_role(payload: dict) -> str:
        roles = payload.get("realm_access", {}).get("roles", [])
        return next((r for r in _ROLE_PRIORITY if r in roles), "readonly")

    @staticmethod
    def _role_from_scopes(scopes: list[str]) -> str:
        for scope, role in _SCOPE_TO_ROLE:
            if scope in scopes:
                return role
        return "readonly"
