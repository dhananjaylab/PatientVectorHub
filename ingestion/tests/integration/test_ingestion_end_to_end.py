"""
End-to-end ingestion integration test — requires the local Docker Compose
stack (postgres + redis + kafka + weaviate; see docker-compose.yml's
Phase 4 additions) or the equivalent CI services (.github/workflows/ci.yml).

R2 is mocked here too, per the CI decision — no live Cloudflare
credentials needed even for this integration test; only
Postgres/Weaviate need to be real, running services for the DB and
vector-store assertions. The embedding call is REAL (OpenAI) since that's
the one piece worth proving end-to-end — this test self-skips if
OPENAI_API_KEY isn't set, so it never fails CI silently for the wrong
reason (see the pytestmark below).
"""
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from sqlalchemy import text as sqltext

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="requires a real OPENAI_API_KEY for the embedding call",
    ),
]

TENANT_A = "00000000-0000-0000-0000-000000000001"  # seeded by scripts/seed_data.py

@pytest.mark.asyncio
async def test_process_document_end_to_end():
    from src.db.session import get_tenant_sync_session
    from src.workers.batch_worker import celery_app, process_document

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())

    with get_tenant_sync_session(TENANT_A) as db:
        db.execute(sqltext(
            "INSERT INTO ingestion_jobs (id, name, status, source_type, doc_count_total, tenant_id)"
            " VALUES (:id, 'e2e-test', 'queued', 's3_batch', 1, :tid)"
        ), {"id": job_id, "tid": TENANT_A})
        db.execute(sqltext(
            "INSERT INTO patients (id, mrn, tenant_id) VALUES (:id, 'vault:v1:E2E', :tid)"
        ), {"id": patient_id, "tid": TENANT_A})
        db.execute(sqltext(
            "INSERT INTO documents (id, patient_id, document_type, source_path,"
            " ingestion_job_id, embedding_status, tenant_id)"
            " VALUES (:id, :pid, 'clinical_note', 'r2://test/e2e-doc.txt', :jid, 'pending', :tid)"
        ), {"id": doc_id, "pid": patient_id, "jid": job_id, "tid": TENANT_A})

    fake_text = b"Patient presents with elevated HbA1c consistent with type 2 diabetes."
    with patch("src.parsers.plain_text_parser.get_object_bytes", return_value=fake_text):
        process_document.apply(kwargs={
            "doc_id": doc_id, "tenant_id": TENANT_A, "job_id": job_id,
            "r2_uri": "r2://test/e2e-doc.txt", "document_type": "clinical_note",
        })

    with get_tenant_sync_session(TENANT_A) as db:
        doc_row = db.execute(
            sqltext("SELECT embedding_status, chunk_count FROM documents WHERE id = :id"),
            {"id": doc_id},
        ).mappings().fetchone()
        job_row = db.execute(
            sqltext("SELECT status, doc_count_processed FROM ingestion_jobs WHERE id = :id"),
            {"id": job_id},
        ).mappings().fetchone()

    assert doc_row["embedding_status"] == "completed"
    assert doc_row["chunk_count"] >= 1
    assert job_row["doc_count_processed"] == 1
    assert job_row["status"] == "completed"
