"""
PatientVectorHub — async DB session management for api-gateway.

Provides get_tenant_session(), the tenant-scoped session helper that
migration 003_enable_rls.py's own docstring flagged as not existing yet:

    "Application code must call SET LOCAL app.tenant_id = '<uuid>' inside
    every request-scoped transaction before touching these tables ...
    Until that helper exists, any connection that does not set
    app.tenant_id will see zero rows from every tenant-scoped table —
    fail-closed by design, not fail-open."

This mirrors scripts/seed_data.py's _set_tenant_context(): it uses
`set_config('app.tenant_id', :tid, true)` (a parameterizable function
call) rather than a literal `SET LOCAL app.tenant_id = '...'` string,
because SET/SET LOCAL cannot take bound parameters over the wire
protocol. `is_local=true` scopes the value to the current transaction, so
it can never leak across requests on a pooled connection.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings

_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)

_session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def get_tenant_session(tenant_id: str) -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession scoped to a single tenant for the duration of
    one transaction. Every tenant-scoped table (users, patients,
    ingestion_jobs, documents, api_keys, audit_logs, query_logs) runs under
    FORCE ROW LEVEL SECURITY, so any statement issued on a session that
    skipped this helper will silently see zero rows rather than raise —
    that's intentional fail-closed behavior, not a bug to work around.

    Usage (typically via the get_db() FastAPI dependency in deps.py):
        async with get_tenant_session(tenant_id) as session:
            await session.execute(...)
            # commit happens automatically on clean exit
    """
    async with _session_factory() as session:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_untenanted_session() -> AsyncIterator[AsyncSession]:
    """Yield a session with NO app.tenant_id set.

    Only safe for genuinely tenant-independent reads — today that's just
    `tenants` itself (see crud.list_tenants / crud.get_tenant). Do NOT use
    this for any of the seven tenant-scoped tables: under FORCE RLS every
    query against them will simply return zero rows here, by design, not
    "work but slower". If you find yourself wanting this for a
    tenant-scoped table, you almost certainly want resolve_api_key_tenant()
    instead (see crud.resolve_api_key and ADR-010) — and that path has its
    own, deliberately narrow, escape hatch.
    """
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Call from the FastAPI lifespan shutdown handler."""
    await _engine.dispose()
