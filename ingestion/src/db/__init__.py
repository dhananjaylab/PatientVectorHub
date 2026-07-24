"""ingestion.src.db — sync, RLS-aware DB access for Celery workers.

Re-exports the most commonly used helpers so existing imports like
`from ..db import get_all_tenant_ids` (doc 34's original pattern) keep
working unchanged."""
from .session import get_all_tenant_ids, get_sync_session, get_tenant_sync_session  # noqa: F401

__all__ = ["get_all_tenant_ids", "get_sync_session", "get_tenant_sync_session"]
