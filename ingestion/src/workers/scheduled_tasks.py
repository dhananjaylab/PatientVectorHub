"""
Celery beat scheduled maintenance tasks (Phase 4 scope, per your decision
to include beat now rather than defer to Phase 10).

Narrower than the original doc 34 design — 'rebuild-bm25' is
intentionally NOT included; BM25/hybrid retrieval doesn't exist until the
RAG engine lands in Phase 7 (see celery_app.py's docstring).

Two tasks:
  - cleanup_completed_jobs   doc 34's original: deletes stale
                             completed/failed ingestion_jobs rows.
  - requeue_stale_documents  NOT in the original design. Added because
                             documents.embedding_status is set to
                             'processing' BEFORE parsing/embedding/upsert
                             happens (batch_worker.py) — if a worker
                             process is killed mid-task (OOM, deploy,
                             spot-instance reclaim) without Celery's own
                             retry firing, that document is stuck in
                             'processing' forever with nothing else to
                             notice. This task finds and requeues them.
                             Idempotent: process_document() overwrites
                             embedding_status regardless of its current
                             value, so double-processing a
                             wrongly-flagged document costs one wasted
                             embedding call, nothing worse.
"""
import logging

from sqlalchemy import text

from ..db.session import get_all_tenant_ids, get_tenant_sync_session
from .celery_app import celery_app

log = logging.getLogger(__name__)

_STALE_JOB_RETENTION = "7 days"
_STALE_PROCESSING_THRESHOLD = "30 minutes"


@celery_app.task(name="pvh.cleanup_completed_jobs")
def cleanup_completed_jobs() -> None:
    for tenant_id in get_all_tenant_ids():
        with get_tenant_sync_session(tenant_id) as db:
            result = db.execute(
                text(
                    "DELETE FROM ingestion_jobs"
                    " WHERE status IN ('completed', 'failed')"
                    "   AND completed_at < NOW() - INTERVAL :age"
                ),
                {"age": _STALE_JOB_RETENTION},
            )
            if result.rowcount:
                log.info(
                    "cleaned up %d stale ingestion_jobs for tenant %s",
                    result.rowcount, tenant_id,
                )


@celery_app.task(name="pvh.requeue_stale_documents")
def requeue_stale_documents() -> None:
    from .batch_worker import process_document  # local import — avoids a
                                                   # celery_app <-> batch_worker
                                                   # import-order issue at module load

    for tenant_id in get_all_tenant_ids():
        with get_tenant_sync_session(tenant_id) as db:
            stale = db.execute(
                text(
                    "SELECT id, document_type, source_path, ingestion_job_id"
                    " FROM documents"
                    " WHERE embedding_status = 'processing'"
                    "   AND ingested_at < NOW() - INTERVAL :threshold"
                ),
                {"threshold": _STALE_PROCESSING_THRESHOLD},
            ).mappings().all()

            for row in stale:
                db.execute(
                    text("UPDATE documents SET embedding_status = 'pending' WHERE id = :id"),
                    {"id": row["id"]},
                )
                process_document.delay(
                    doc_id=str(row["id"]),
                    tenant_id=tenant_id,
                    job_id=str(row["ingestion_job_id"]) if row["ingestion_job_id"] else "",
                    r2_uri=row["source_path"],
                    document_type=row["document_type"],
                )
                log.warning("requeued stale document %s (tenant %s)", row["id"], tenant_id)
