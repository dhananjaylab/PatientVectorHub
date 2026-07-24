"""
Sync DB session helpers for Celery workers (ingestion service).

Extends the Phase 1 stub with real RLS-aware tenant scoping, mirroring
api-gateway/src/db/session.py::get_tenant_session() and
scripts/seed_data.py::_set_tenant_context() — both already established
the set_config('app.tenant_id', tid, true) pattern this file reuses (not
a literal `SET LOCAL ...` string — SET/SET LOCAL cannot bind parameters
over the wire protocol).

Required because migration 003_enable_rls.py / 004_add_core_tables.py put
ingestion_jobs, documents, patients, etc. under FORCE ROW LEVEL SECURITY;
the Phase 1 get_sync_session() had NO tenant scoping at all and would
silently see zero rows against any non-superuser DB role (Aiven included
— see ADR-010's identical caveat for the API-key resolver).
"""
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from ..config import settings

_engine = create_engine(
    settings.DATABASE_URL_SYNC,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)


def get_all_tenant_ids() -> list[str]:
    """Real query — replaces the Phase 1 hardcoded tenant pair."""
    with _engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM tenants"))
        return [str(r[0]) for r in rows]


@contextmanager
def get_tenant_sync_session(tenant_id: str) -> Iterator[Session]:
    """Yield a tenant-scoped sync Session for exactly one transaction.
    Every write inside the `with` block is subject to FORCE ROW LEVEL
    SECURITY, scoped to tenant_id — commits on clean exit, rolls back on
    exception. This is the ONLY session helper ingestion write paths
    (crud.py, batch_worker.py, scheduled_tasks.py) should use."""
    with Session(_engine) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def get_sync_session() -> Iterator[Session]:
    """Untenanted session — only safe for genuinely tenant-independent
    reads (today: get_all_tenant_ids's own use via a raw connection, and
    nothing else). Kept for backward compatibility with any Phase 1 code
    that imported this name directly; new code should use
    get_tenant_sync_session()."""
    with Session(_engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
