# ADR-010: API-Key Authentication vs. RLS Bootstrapping (Fail-Closed Interim State)

**Date:** 2026-07-19
**Status:** Accepted (interim — see "Consequences" for the follow-up this defers)
**Relates to:** migration 003_enable_rls.py, migration 004_add_core_tables.py,
`api-gateway/src/middleware/auth.py`, `api-gateway/src/db/crud.py::resolve_api_key`

## Context

doc 09 (API Contracts) specifies two credential types: `Authorization: Bearer
<keycloak_jwt>` for human users, and `X-API-Key: <key>` for service accounts,
validated against the `api_keys` table (SHA256 hash, never plaintext).

`api_keys` is tenant-scoped and — like every other tenant-scoped table since
migration 003 — runs under `FORCE ROW LEVEL SECURITY` with a policy requiring
`tenant_id = current_setting('app.tenant_id', true)::uuid`. That policy is
exactly what makes cross-tenant queries fail closed everywhere else in the
system. It also creates a genuine bootstrapping problem specifically for API
key authentication: resolving an inbound raw key to "which tenant does this
belong to" is precisely the query that would need `app.tenant_id` set before
it can run — but you don't know the tenant until this query resolves it.

This is not a new category of problem for this codebase. `scripts/seed_data.py`
and `.github/workflows/ci.yml`'s "Create RLS test role" step already document
and solve an adjacent version of it: the app's normal DB role (`pvh` locally,
whatever Aiven issues in cloud environments) is not reliably a Postgres
superuser or `BYPASSRLS`-flagged role, so anything that needs to read across
the RLS boundary needs a deliberately narrow, separately-provisioned role —
not a weakening of the policy itself.

## Decision

`resolve_api_key_tenant(p_key_hash text)` (migration 004) is a `SECURITY
DEFINER` SQL function that looks up `api_keys` by hash without an
`app.tenant_id` precondition. In Postgres, a `SECURITY DEFINER` function
executes as its owning role for both permission checks and RLS applicability.
Verified empirically against a real Postgres 16 instance (not just reasoned
about) with a genuine non-superuser, `NOBYPASSRLS` caller role — mirroring
CI's own `pvh_rls_test` — the precise behavior is:

| Function owner | `SELECT` grant on `api_keys`? | Result for a non-superuser caller |
|---|---|---|
| Superuser (e.g. local Docker Compose's `pvh`) | n/a | **Works immediately** — superusers unconditionally bypass RLS in Postgres; `FORCE ROW LEVEL SECURITY` does not override that. No extra provisioning needed locally, consistent with `scripts/seed_data.py`'s existing "local `pvh` is a bootstrap superuser" caveat. |
| Non-superuser, **no** `BYPASSRLS` | doesn't matter | **Zero rows returned — no error.** This is the true "unprovisioned" state most managed-Postgres environments start in (Aiven's `avnadmin`, RDS's master user, etc. are deliberately *not* true superusers). |
| Non-superuser, **has** `BYPASSRLS` | **required** | Works — but `BYPASSRLS` alone is not sufficient; the owning role also needs an ordinary object-level `SELECT` grant on `api_keys`, since `BYPASSRLS` only bypasses row-security *policies*, not table-level permissions. Confirmed by reproducing "permission denied for table api_keys" with `BYPASSRLS` granted but `SELECT` missing. |

So on any environment where the migrating role is a genuine Postgres
superuser (local dev), this already works with zero extra steps. On managed
Postgres where it isn't (Aiven, RDS, Cloud SQL), a DB admin must separately
grant both `BYPASSRLS` **and** `SELECT ON api_keys` to the function's owning
role, **outside Alembic** — `ALTER ROLE ... CREATE ROLE` privileges are not
reliably available to the app's own migrating role on managed Postgres, the
same reason CI provisions `pvh_rls_test` via a shell step rather than a
migration.

Until both grants exist in a given environment, `resolve_api_key_tenant()`
returns zero rows for every call — not an error, not a fallback to an
unscoped read, just zero rows. `db.crud.resolve_api_key()` treats "zero rows"
identically to "key not found," and `middleware.auth.KeycloakJWTMiddleware`
returns the same generic `401 AUTHENTICATION_FAILED` either way. **API-key
authentication fails closed by construction**: an unprovisioned environment
rejects every API key rather than silently granting cross-tenant access, and
the failure is deliberately indistinguishable from "invalid key" to the
caller — an environment-provisioning gap should never be observable
externally as anything other than "unauthenticated."

JWT-based (Keycloak) authentication has no equivalent gap: the tenant_id
comes from a claim embedded in an already-verified, signed token, so there's
no "look up the tenant first" step to bootstrap.

## Consequences

- **API-key authentication works with zero extra setup in local Docker
  Compose dev** (the `pvh` role is a bootstrap superuser there — see table
  above) **but not yet in any non-superuser environment (Aiven included)**
  until an admin runs the grants below. This is expected, not a bug to
  chase, for Phase 2/3 — Aiven-specific provisioning was never going to be
  exercised by local development anyway, and ingestion/query routes that
  would actually consume API keys are Phase 4/7/8 work regardless.
- Required grants, once per non-superuser environment:
  ```sql
  -- Run once by a DB admin, NOT via Alembic:
  CREATE ROLE pvh_key_resolver NOLOGIN NOSUPERUSER BYPASSRLS;
  GRANT SELECT ON api_keys TO pvh_key_resolver;  -- BYPASSRLS alone is not
                                                   -- enough; it bypasses RLS
                                                   -- policies, not table-
                                                   -- level GRANTs, which are
                                                   -- a separate permission
                                                   -- system entirely.
  ALTER FUNCTION resolve_api_key_tenant(text) OWNER TO pvh_key_resolver;
  ```
  (`NOLOGIN` is sufficient — the app never connects *as* this role; it only
  needs to own the function so the function body runs with its privileges.)
- **Do not** "fix" API-key auth by loosening the RLS policy on `api_keys`,
  disabling `FORCE ROW LEVEL SECURITY`, or having the app's primary
  `DATABASE_URL` role bypass RLS generally — any of those would remove the
  tenant-isolation guarantee from every other table too, not just solve the
  bootstrapping problem for this one lookup.
- Follow-up ADR needed before Phase 8 (REST API) ships API-key-authenticated
  routes for real: confirm Aiven grants `CREATEROLE`/`BYPASSRLS` assignment
  to the app's admin credentials, or decide on an alternative bootstrapping
  mechanism (e.g., a narrow Vault-issued dynamic credential) if not.
- `request.state.scopes` is populated on successful API-key auth and is
  intentionally unused by `middleware.rbac` today (scopes are collapsed to
  a derived `role` — see `middleware/auth.py`'s `_SCOPE_TO_ROLE` mapping).
  Revisit if/when a route needs true per-scope authorization independent of
  the role hierarchy.

## References

- `api-gateway/migrations/versions/003_enable_rls.py`
- `api-gateway/migrations/versions/004_add_core_tables.py`
- `api-gateway/src/middleware/auth.py`
- `api-gateway/src/db/crud.py::resolve_api_key`
- `scripts/seed_data.py` (`_set_tenant_context` docstring — the adjacent,
  already-solved version of this problem)
- `.github/workflows/ci.yml` ("Create RLS test role" step)
- Docs 09 (API Contracts), 26 (Audit Middleware & RBAC — original
  `require_role`/`require_min_role` design, superseded in detail by
  `middleware/rbac.py` but not in intent)
