"""
Unit tests for api-gateway/src/routers/ingest.py.

create_job had no dedicated unit test before Phase 8 despite shipping in
Phase 4 (only exercised indirectly, if at all, via integration tests
requiring a live stack); get_job and list_jobs had none at all. This
file closes that gap and covers list_jobs's new real pagination
(ADR-015) — it previously called crud.list_ingestion_jobs(db,
status=status) with no limit/offset support at all (that function itself
was hardcoded to LIMIT 100). Same standalone-app harness as
test_query_router.py / test_audit_router.py / test_admin_router.py.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _build_app(role: str = "engineer", tenant_id: str = "tenant-a", user_id: str = "user-1"):
    from src.deps import get_db
    from src.routers.ingest import router
    from starlette.middleware.base import BaseHTTPMiddleware

    app = FastAPI()
    app.state.kafka = AsyncMock()

    class _FakeAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            request.state.user_id = user_id
            request.state.tenant_id = tenant_id
            request.state.role = role
            request.state.email = None
            request.state.auth_method = "jwt"
            request.state.api_key_id = None
            request.state.scopes = []
            return await call_next(request)

    app.add_middleware(_FakeAuthMiddleware)
    app.include_router(router, prefix="/v1/ingest")

    async def _fake_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_get_db
    return app


BELOW_ENGINEER_ROLES = ["analyst", "auditor", "readonly"]

_VALID_JOB_BODY = {
    "name": "nightly-batch",
    "source_type": "s3_batch",
    "documents": [
        {
            "source_path": "r2://bucket/a.txt",
            "document_type": "clinical_note",
            "patient_id": str(uuid.uuid4()),
        },
        {
            "source_path": "r2://bucket/b.txt",
            "document_type": "lab_result",
            "patient_id": str(uuid.uuid4()),
        },
    ],
}


def _mock_job_row(**overrides) -> dict:
    row = {
        "id": uuid.uuid4(),
        "name": "nightly-batch",
        "status": "queued",
        "source_type": "s3_batch",
        "doc_count_total": 2,
        "doc_count_processed": 0,
        "doc_count_failed": 0,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
        "created_at": datetime.datetime(2026, 8, 15, tzinfo=datetime.timezone.utc),
    }
    row.update(overrides)
    row.setdefault("progress_pct", 0.0)
    return row


class TestCreateJob:
    @pytest.mark.asyncio
    async def test_engineer_creates_job_and_publishes_one_message_per_document(self):
        app = _build_app(role="engineer", user_id="eng-1")
        job_row = _mock_job_row()
        with (
            patch(
                "src.routers.ingest.crud.create_ingestion_job",
                new=AsyncMock(return_value={"id": job_row["id"], "status": "queued"}),
            ),
            patch("src.routers.ingest.crud.set_job_doc_count_total", new=AsyncMock()),
            patch(
                "src.routers.ingest.crud.create_document",
                new=AsyncMock(side_effect=[{"id": uuid.uuid4()}, {"id": uuid.uuid4()}]),
            ),
            patch(
                "src.routers.ingest.publish_document_ingest", new=AsyncMock()
            ) as mocked_publish,
            patch("src.routers.ingest.crud.write_audit_log", new=AsyncMock()) as mocked_audit,
            patch(
                "src.routers.ingest.crud.get_ingestion_job", new=AsyncMock(return_value=job_row)
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.post("/v1/ingest/jobs", json=_VALID_JOB_BODY)

        assert resp.status_code == 201
        assert resp.json()["status"] == "queued"
        assert mocked_publish.await_count == 2  # one Kafka message per document
        mocked_audit.assert_called_once()
        assert mocked_audit.call_args.kwargs["action"] == "document_ingest"
        assert mocked_audit.call_args.kwargs["metadata"]["doc_count"] == 2

    @pytest.mark.asyncio
    async def test_admin_also_allowed_engineer_plus(self):
        app = _build_app(role="admin")
        job_row = _mock_job_row()
        with (
            patch(
                "src.routers.ingest.crud.create_ingestion_job",
                new=AsyncMock(return_value={"id": job_row["id"], "status": "queued"}),
            ),
            patch("src.routers.ingest.crud.set_job_doc_count_total", new=AsyncMock()),
            patch(
                "src.routers.ingest.crud.create_document",
                new=AsyncMock(side_effect=[{"id": uuid.uuid4()}, {"id": uuid.uuid4()}]),
            ),
            patch("src.routers.ingest.publish_document_ingest", new=AsyncMock()),
            patch("src.routers.ingest.crud.write_audit_log", new=AsyncMock()),
            patch(
                "src.routers.ingest.crud.get_ingestion_job", new=AsyncMock(return_value=job_row)
            ),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.post("/v1/ingest/jobs", json=_VALID_JOB_BODY)
        assert resp.status_code == 201

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", BELOW_ENGINEER_ROLES)
    async def test_below_engineer_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.ingest.crud.create_ingestion_job", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.post("/v1/ingest/jobs", json=_VALID_JOB_BODY)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_empty_documents_list_is_422(self):
        app = _build_app(role="engineer")
        body = {**_VALID_JOB_BODY, "documents": []}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.post("/v1/ingest/jobs", json=body)
        assert resp.status_code == 422


class TestGetJob:
    @pytest.mark.asyncio
    async def test_engineer_gets_existing_job(self):
        app = _build_app(role="engineer")
        job_row = _mock_job_row(status="running", doc_count_processed=1)
        with patch(
            "src.routers.ingest.crud.get_ingestion_job", new=AsyncMock(return_value=job_row)
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get(f"/v1/ingest/jobs/{job_row['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    @pytest.mark.asyncio
    async def test_missing_job_is_404(self):
        app = _build_app(role="engineer")
        with patch("src.routers.ingest.crud.get_ingestion_job", new=AsyncMock(return_value=None)):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/ingest/jobs/does-not-exist")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", BELOW_ENGINEER_ROLES)
    async def test_below_engineer_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.ingest.crud.get_ingestion_job", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/ingest/jobs/some-id")
        assert resp.status_code == 403


class TestListJobs:
    @pytest.mark.asyncio
    async def test_default_pagination(self):
        app = _build_app(role="engineer")
        rows = [_mock_job_row(), _mock_job_row(name="second-batch")]
        with patch(
            "src.routers.ingest.crud.list_ingestion_jobs",
            new=AsyncMock(return_value={"jobs": rows, "total": 2}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/ingest/jobs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert len(body["jobs"]) == 2
        assert mocked.call_args.kwargs["limit"] == 50
        assert mocked.call_args.kwargs["offset"] == 0

    @pytest.mark.asyncio
    async def test_custom_limit_offset_and_status_filter_passed_through(self):
        app = _build_app(role="engineer")
        with patch(
            "src.routers.ingest.crud.list_ingestion_jobs",
            new=AsyncMock(return_value={"jobs": [], "total": 0}),
        ) as mocked:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                await c.get(
                    "/v1/ingest/jobs", params={"status": "failed", "limit": 10, "offset": 20}
                )
        assert mocked.call_args.kwargs["status"] == "failed"
        assert mocked.call_args.kwargs["limit"] == 10
        assert mocked.call_args.kwargs["offset"] == 20

    @pytest.mark.asyncio
    async def test_limit_over_200_is_422(self):
        app = _build_app(role="engineer")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/v1/ingest/jobs", params={"limit": 9999})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_offset_is_422(self):
        app = _build_app(role="engineer")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            resp = await c.get("/v1/ingest/jobs", params={"offset": -5})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", BELOW_ENGINEER_ROLES)
    async def test_below_engineer_rejected_403(self, role):
        app = _build_app(role=role)
        with patch("src.routers.ingest.crud.list_ingestion_jobs", new=AsyncMock()):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                resp = await c.get("/v1/ingest/jobs")
        assert resp.status_code == 403
