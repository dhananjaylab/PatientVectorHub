"""
PatientVectorHub — ingestion job routes (Phase 4; rate limits + real
pagination added Phase 8 / ADR-015).

POST /v1/ingest/jobs creates the ingestion_jobs row AND one documents row
per submitted DocumentRef, then publishes one doc-ingest Kafka message
per document — see kafka_utils.py's docstring for why per-document, not
per-job.

Requires request.app.state.kafka (an AIOKafkaProducer) to already be
started by main.py's lifespan — verify this exists before mounting this
router; see MANUAL_INTEGRATION_NOTES.md if it doesn't yet.

Phase 8 changes:
  - All three routes gained `request: Request` + `response: Response`
    params (get_job/list_jobs didn't have `request` at all before; create_job
    already did) and a `@limiter.limit(...)` decorator matching doc 09's
    rate-limit table — see middleware/rate_limit.py's docstring for why
    both params are required by the decorator.
  - list_jobs gained real limit/offset query params and a total count.
    It previously called crud.list_ingestion_jobs(db, status=status) with
    no pagination args at all — that function itself was hardcoded to
    `LIMIT 100`, no offset, no total (see db/crud.py's Phase 8 docstring
    for the crud-layer half of this fix). The response envelope gained
    `total`/`limit`/`offset` alongside the existing `jobs` list; no
    response_model was ever declared on this route, so FastAPI's default
    jsonable_encoder continues to handle the UUID/datetime fields inside
    each job dict exactly as it always has — no new serialization needed
    here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..db import crud
from ..deps import get_current_user, get_db
from ..kafka_utils import publish_document_ingest
from ..middleware.rate_limit import limiter
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
@limiter.limit("100/minute")  # doc 09: POST /v1/ingest/jobs — 100/min
async def create_job(
    body: IngestJobCreate,
    request: Request,
    response: Response,
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
@limiter.limit("500/minute")  # doc 09: GET /v1/ingest/jobs/{id} — 500/min
async def get_job(
    job_id: str,
    request: Request,
    response: Response,
    db=Depends(get_db),
) -> IngestJobResponse:
    job = await crud.get_ingestion_job(db, job_id=job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return _to_response(job)


@router.get("/jobs", dependencies=[require_min_role("engineer")])
@limiter.limit("200/minute")  # not in doc 09's original table; matches admin.py's read default
async def list_jobs(
    request: Request,
    response: Response,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
) -> dict:
    result = await crud.list_ingestion_jobs(db, status=status, limit=limit, offset=offset)
    return {"jobs": result["jobs"], "total": result["total"], "limit": limit, "offset": offset}
