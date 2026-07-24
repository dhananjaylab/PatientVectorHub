"""
Sync CRUD for ingestion Celery workers — tenant-scoped, RLS-safe.

Every function here requires a tenant_id and writes through
get_tenant_sync_session(), never the untenanted get_sync_session().

update_job_progress / mark_document_failed do NOT exist anywhere in the
pre-Phase-4 codebase — they were sketched in the original reference docs
(31/34) for the async api-gateway crud.py but that file stopped short of
adding them, and no sync equivalent existed for the ingestion side at
all. This is genuinely new code, not a port.
"""
from sqlalchemy import text

from .session import get_tenant_sync_session


def update_job_progress(tenant_id: str, job_id: str, increment: int = 1) -> None:
    """Atomically increment doc_count_processed; auto-transition the job
    to 'completed' once processed+failed reaches doc_count_total (kept
    intentionally the same regardless of how many of those were failures
    — see docs/PHASE_4_IMPLEMENTATION_PLAN.md §5 for why "completed" vs.
    "completed_with_errors" is decided at the API layer, not here)."""
    with get_tenant_sync_session(tenant_id) as db:
        db.execute(
            text(
                "UPDATE ingestion_jobs SET"
                " doc_count_processed = doc_count_processed + :n,"
                " started_at = COALESCE(started_at, NOW()),"
                " status = CASE"
                "   WHEN doc_count_total > 0"
                "    AND doc_count_processed + :n + doc_count_failed >= doc_count_total"
                "   THEN 'completed' ELSE 'running' END,"
                " completed_at = CASE"
                "   WHEN doc_count_total > 0"
                "    AND doc_count_processed + :n + doc_count_failed >= doc_count_total"
                "   THEN NOW() ELSE completed_at END"
                " WHERE id = :jid"
            ),
            {"n": increment, "jid": job_id},
        )


def mark_document_failed(tenant_id: str, document_id: str, job_id: str, error: str) -> None:
    """Mark a single document embedding_status='failed' and bump the
    parent job's doc_count_failed + completion check, in one transaction.
    Called from batch_worker.py's terminal-failure path (retries
    exhausted) — see plan §6 for why this is paired with a Kafka doc-dlq
    publish, not a substitute for it."""
    with get_tenant_sync_session(tenant_id) as db:
        db.execute(
            text("UPDATE documents SET embedding_status = 'failed' WHERE id = :did"),
            {"did": document_id},
        )
        db.execute(
            text(
                "UPDATE ingestion_jobs SET"
                " doc_count_failed = doc_count_failed + 1,"
                " error_message = COALESCE(error_message || ' | ', '') || :err,"
                " status = CASE"
                "   WHEN doc_count_total > 0"
                "    AND doc_count_processed + doc_count_failed + 1 >= doc_count_total"
                "   THEN 'completed' ELSE 'running' END,"
                " completed_at = CASE"
                "   WHEN doc_count_total > 0"
                "    AND doc_count_processed + doc_count_failed + 1 >= doc_count_total"
                "   THEN NOW() ELSE completed_at END"
                " WHERE id = :jid"
            ),
            {"err": error[:500], "jid": job_id},
        )


def update_document_embedding_status(
    tenant_id: str,
    document_id: str,
    status: str,
    chunk_count: int | None = None,
    model_version: str | None = None,
) -> None:
    """Transition documents.embedding_status: pending -> processing ->
    completed|failed (all four values are covered by migration 004's
    CHECK constraint). chunk_count/model_version are only overwritten
    when actually supplied, via COALESCE."""
    with get_tenant_sync_session(tenant_id) as db:
        db.execute(
            text(
                "UPDATE documents SET"
                " embedding_status = :status,"
                " chunk_count = COALESCE(:chunk_count, chunk_count),"
                " model_version = COALESCE(:model_version, model_version)"
                " WHERE id = :did"
            ),
            {
                "status": status,
                "chunk_count": chunk_count,
                "model_version": model_version,
                "did": document_id,
            },
        )
