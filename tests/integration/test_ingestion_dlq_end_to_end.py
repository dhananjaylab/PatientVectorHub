"""
Forces a parser failure and confirms the terminal-failure path actually
lands a message on doc-dlq (a REAL Kafka topic here, not mocked) and
updates document/job state — closing the gap flagged in
docs/PHASE_4_IMPLEMENTATION_PLAN.md §6. Requires Kafka + Postgres
running; R2 is mocked per the CI decision.

Uses Celery's Task.apply(..., retries=N) to simulate "final attempt"
directly rather than looping through real retry mechanics — see
tests/unit/test_ingestion_dlq.py's module docstring for why.
"""
import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv
from sqlalchemy import text as sqltext

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ingestion"))

pytestmark = pytest.mark.integration

TENANT_A = "00000000-0000-0000-0000-000000000001"


async def _consume_one_dlq_message(timeout: float = 15.0) -> dict | None:
    from aiokafka import AIOKafkaConsumer
    from src.config import settings

    consumer = AIOKafkaConsumer(
        "doc-dlq",
        bootstrap_servers=settings.KAFKA_BROKERS,
        group_id=f"dlq-test-{uuid.uuid4()}",   # fresh group -> reads from the start
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    await consumer.start()
    try:
        result = await asyncio.wait_for(consumer.getone(), timeout=timeout)
        return json.loads(result.value)
    except asyncio.TimeoutError:
        return None
    finally:
        await consumer.stop()


@pytest.mark.asyncio
async def test_forced_failure_lands_on_dlq_and_marks_document_failed():
    from src.db.session import get_tenant_sync_session
    from src.workers.batch_worker import celery_app, process_document

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False

    job_id = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    patient_id = str(uuid.uuid4())

    with get_tenant_sync_session(TENANT_A) as db:
        db.execute(sqltext(
            "INSERT INTO ingestion_jobs (id, name, status, source_type, doc_count_total, tenant_id)"
            " VALUES (:id, 'dlq-test', 'queued', 's3_batch', 1, :tid)"
        ), {"id": job_id, "tid": TENANT_A})
        db.execute(sqltext(
            "INSERT INTO patients (id, mrn, tenant_id) VALUES (:id, 'vault:v1:DLQ', :tid)"
        ), {"id": patient_id, "tid": TENANT_A})
        db.execute(sqltext(
            "INSERT INTO documents (id, patient_id, document_type, source_path,"
            " ingestion_job_id, embedding_status, tenant_id)"
            " VALUES (:id, :pid, 'clinical_note', 'r2://test/corrupt.pdf', :jid, 'pending', :tid)"
        ), {"id": doc_id, "pid": patient_id, "jid": job_id, "tid": TENANT_A})

    with patch(
        "src.workers.batch_worker.get_parser_for_uri",
        side_effect=RuntimeError("simulated corrupt document"),
    ):
        # retries=3 == max_retries -> terminal failure on this attempt
        process_document.apply(
            kwargs={
                "doc_id": doc_id, "tenant_id": TENANT_A, "job_id": job_id,
                "r2_uri": "r2://test/corrupt.pdf", "document_type": "clinical_note",
            },
            retries=3,
        )

    dlq_message = await _consume_one_dlq_message()
    assert dlq_message is not None, "expected a message on doc-dlq within the timeout"
    assert dlq_message["doc_id"] == doc_id
    assert "simulated corrupt document" in dlq_message["error"]

    with get_tenant_sync_session(TENANT_A) as db:
        doc_row = db.execute(
            sqltext("SELECT embedding_status FROM documents WHERE id = :id"), {"id": doc_id},
        ).mappings().fetchone()
        job_row = db.execute(
            sqltext("SELECT doc_count_failed FROM ingestion_jobs WHERE id = :id"), {"id": job_id},
        ).mappings().fetchone()

    assert doc_row["embedding_status"] == "failed"
    assert job_row["doc_count_failed"] == 1
