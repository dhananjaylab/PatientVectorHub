"""
Pydantic request/response models for POST/GET /v1/ingest/jobs.

Design note (Phase 4): unlike the original doc 32 sketch (a bare S3
prefix), IngestJobCreate requires an explicit `documents` list. This lets
the API create one `documents` row per item up front and publish one
Kafka message per document (matching doc-ingest's 12-partition design —
see kafka_utils.py) instead of requiring the worker to enumerate an R2
prefix itself. For very large batches (10k+), consider a manifest-file
URI instead of an inline JSON array — flagged as a Phase 4+ enhancement,
not blocking; scripts/load_test_ingestion.py bypasses this constraint
entirely by talking to the DB/Celery layer directly for load testing.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class DocumentRef(BaseModel):
    source_path: str = Field(..., description="r2://bucket/key/... URI of the raw document")
    document_type: str = Field(
        ...,
        pattern="^(clinical_note|lab_result|imaging_report|discharge_summary|prescription)$",
    )
    patient_id: str = Field(..., description="UUID of the patient this document belongs to")


class IngestJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    source_type: str = Field(default="s3_batch", pattern="^(s3_batch|kafka_stream|api_push)$")
    documents: list[DocumentRef] = Field(..., min_length=1, max_length=5000)
    embedding_model: str = "text-embedding-3-large"
    chunk_size: int = Field(default=512, ge=64, le=2048)
    chunk_overlap: int = Field(default=50, ge=0, le=256)


class IngestJobResponse(BaseModel):
    job_id: str
    status: str
    doc_count_total: int = 0
    doc_count_processed: int = 0
    doc_count_failed: int = 0
    progress_pct: float = 0.0
    error_message: str | None = None
    created_at: str | None = None

    @computed_field  # type: ignore[misc]
    @property
    def display_status(self) -> str:
        """API-layer-only label (decision: no new DB status value — see
        docs/PHASE_4_IMPLEMENTATION_PLAN.md §5). Never persisted, only
        computed on the way out of the API."""
        if self.status == "completed" and self.doc_count_failed > 0:
            return "completed_with_errors"
        return self.status
