"""
PatientVectorHub — ingestion job routes (Phase 4).

POST /v1/ingest/jobs creates the ingestion_jobs row AND one documents row
per submitted DocumentRef, then publishes one doc-ingest Kafka message
per document — see kafka_utils.py's docstring for why per-document, not
per-job.

Requires request.app.state.kafka (an AIOKafkaProducer) to already be
started by main.py's lifespan — verify this exists before mounting this
router; see MANUAL_INTEGRATION_NOTES.md if it doesn't yet.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from starlette.requests import Request

from ..db import crud
from ..deps import get_current_user, get_db
from ..kafka_utils import publish_document_ingest
from ..middleware.rbac import require_min_role
from ..schemas.ingest import IngestJobCreate, IngestJobResponse

router = APIRouter()


def _to_response(job: dict) -> IngestJobResponse:
    return IngestJobResponse(
        job_id=str(job["id"]),
        status=job["status"],
        doc_count_total=job["doc_count_total"],
        doc_count_processed=job["doc_count_processed"],
        doc_count_failed=job["doc_count_failed"],
        progress_pct=job.get("progress_pct", 0.0),
        error_message=job.get("error_message"),
        created_at=job["created_at"].isoformat() if job.get("created_at") else None,
    )


@router.post(
    "/jobs",
    response_model=IngestJobResponse,
    status_code=201,
    dependencies=[require_min_role("engineer")],
)
async def create_job(
    body: IngestJobCreate,
    request: Request,
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> IngestJobResponse:
    job = await crud.create_ingestion_job(
        db,
        name=body.name,
        source_type=body.source_type,
        source_config={"document_count": len(body.documents)},
        created_by=user["user_id"],
    )
    job_id = job["id"]

    # doc_count_total isn't set by create_ingestion_job (column default is
    # 0) — set it now that we know exactly how many documents this job covers.
    await crud.set_job_doc_count_total(db, job_id=job_id, total=len(body.documents))

    kafka = request.app.state.kafka
    for doc_ref in body.documents:
        doc = await crud.create_document(
            db,
            patient_id=doc_ref.patient_id,
            document_type=doc_ref.document_type,
            source_path=doc_ref.source_path,
            ingestion_job_id=job_id,
        )
        await publish_document_ingest(
            kafka,
            doc_id=doc["id"],
            job_id=job_id,
            tenant_id=user["tenant_id"],
            source_path=doc_ref.source_path,
            document_type=doc_ref.document_type,
            embedding_model=body.embedding_model,
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )

    await crud.write_audit_log(
        db,
        action="document_ingest",
        user_id=user["user_id"],
        metadata={"job_id": job_id, "doc_count": len(body.documents)},
    )

    created = await crud.get_ingestion_job(db, job_id=job_id)
    return _to_response(created)


@router.get(
    "/jobs/{job_id}",
    response_model=IngestJobResponse,
    dependencies=[require_min_role("engineer")],
)
async def get_job(job_id: str, db=Depends(get_db)) -> IngestJobResponse:
    job = await crud.get_ingestion_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return _to_response(job)


@router.get("/jobs", dependencies=[require_min_role("engineer")])
async def list_jobs(status: str | None = None, db=Depends(get_db)) -> dict:
    jobs = await crud.list_ingestion_jobs(db, status=status)
    return {"jobs": jobs}
