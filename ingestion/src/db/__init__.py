"""
Synchronous database helpers for Celery workers.
Phase 1: stubs only. Real CRUD added in Phase 4 when Alembic
migrations and models are in place.
"""
from contextlib import contextmanager
import os


def get_all_tenant_ids() -> list[str]:
    """Return all active tenant IDs from the database.
    Phase 4: replaced with real SELECT id FROM tenants query.
    """
    # Hardcoded seeded IDs for Phase 1/2 development
    return [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]


@contextmanager
def get_sync_session():
    """Yield a synchronous SQLAlchemy session.
    Phase 4: wires real CloudNativePG connection.
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        url = os.getenv(
            "DATABASE_URL_SYNC",
            "postgresql+psycopg2://pvh:pvh_local@localhost:5432/pvh",
        ).replace("postgresql+asyncpg", "postgresql+psycopg2")

        engine = create_engine(url, pool_pre_ping=True)
        with Session(engine) as session:
            yield session
    except ImportError:
        # Phase 1: SQLAlchemy may not be installed in all envs
        yield None
