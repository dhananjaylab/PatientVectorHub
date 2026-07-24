"""
Celery batch-ingestion worker — the core of Phase 4.

process_document() ties together parsing (ingestion/src/parsers/),
chunking (ingestion/src/chunkers/), embedding (ingestion/src/embeddings/),
vector storage (vector_store.WeaviateStore — ADR-011, native
multi-tenancy per ADR-009), and job/document progress tracking
(ingestion/src/db/crud.py) into one task, with terminal failures routed
to the Kafka doc-dlq topic explicitly — see
docs/PHASE_4_IMPLEMENTATION_PLAN.md §6 for why that routing has to be
explicit here rather than left to Celery's own retry-exhaustion
bookkeeping (the reference docs never actually wired this up).

Cross-package import note: `from vector_store.interface import ...`
requires the vector-store/src package to be importable from ingestion's
runtime — see MANUAL_INTEGRATION_NOTES.md for exactly what that requires
(this repo's per-service-venv layout doesn't do this automatically).
"""
import asyncio
import logging

from .celery_app import celery_app
from ..chunkers.splitter import RawChunk, chunk_text
from ..config import settings
from ..db.crud import mark_document_failed, update_document_embedding_status, update_job_progress
from ..embeddings.openai_embedder import embed_batch
from ..parsers import get_parser_for_uri
from .dlq_producer import publish_to_dlq_sync

log = logging.getLogger(__name__)


def _to_vector_chunks(raw_chunks: list[RawChunk], document_type: str, patient_id_hash: str):
    """Bridge ingestion's dependency-free RawChunk to vector_store's Chunk
    contract, at the one place that actually needs both packages."""
    from vector_store.interface import Chunk  # local import — see module docstring

    return [
        Chunk(
            text=rc.text,
            index=rc.index,
            metadata={"document_type": document_type, "patient_id_hash": patient_id_hash},
        )
        for rc in raw_chunks
    ]


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    queue="doc-ingest",
    name="pvh.process_document",
)
def process_document(
    self,
    doc_id: str,
    tenant_id: str,
    job_id: str,
    r2_uri: str,
    document_type: str = "clinical_note",
    patient_id_hash: str = "",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> None:
    try:
        update_document_embedding_status(tenant_id, doc_id, "processing")

        raw_text = get_parser_for_uri(r2_uri).extract(r2_uri)
        raw_chunks = chunk_text(raw_text, chunk_size=chunk_size, overlap=chunk_overlap)
        if not raw_chunks:
            raise ValueError(f"No extractable text in {r2_uri!r}")

        vectors = asyncio.run(embed_batch([c.text for c in raw_chunks]))
        chunks = _to_vector_chunks(raw_chunks, document_type, patient_id_hash)

        from vector_store.interface import get_store  # local import — see module docstring
        store = get_store(tenant_id)
        asyncio.run(store.upsert(doc_id, chunks, vectors))

        update_document_embedding_status(
            tenant_id, doc_id, "completed",
            chunk_count=len(chunks), model_version=settings.EMBEDDING_MODEL_VERSION,
        )
        update_job_progress(tenant_id, job_id, increment=1)
        log.info("processed doc_id=%s job_id=%s chunks=%d", doc_id, job_id, len(chunks))

    except Exception as exc:
        log.error(
            "process_document failed doc_id=%s attempt=%d/%d: %s",
            doc_id, self.request.retries, self.max_retries, exc,
        )
        if self.request.retries >= self.max_retries:
            # Terminal failure. Route to Kafka DLQ, mark the document
            # failed, and let the task end cleanly — do NOT call
            # self.retry() again here, or Celery's own retry bookkeeping
            # fights the DLQ routing (see plan §6).
            publish_to_dlq_sync(
                payload={
                    "doc_id": doc_id, "job_id": job_id, "tenant_id": tenant_id,
                    "r2_uri": r2_uri, "document_type": document_type,
                },
                error=str(exc),
            )
            mark_document_failed(tenant_id, doc_id, job_id, str(exc))
            return
        raise self.retry(exc=exc)
