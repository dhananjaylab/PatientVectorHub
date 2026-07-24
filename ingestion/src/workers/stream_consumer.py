"""
Kafka stream consumer — dispatches each doc-ingest message as a Celery
task. Manual offset commit only after successful dispatch, so a crash
between receiving and dispatching redelivers the message rather than
silently dropping it (doc 21's original pattern — it was already
correct, kept as-is).

Design note: EVERY document — regardless of ingestion_jobs.source_type
('s3_batch' or 'api_push') — flows through this consumer. The API
(api-gateway/src/routers/ingest.py) publishes one doc-ingest message per
document rather than one per job, specifically so this consumer and
doc-ingest's 12 partitions do the fan-out, not a single worker
enumerating a whole batch inline. See
api-gateway/src/kafka_utils.py's docstring for the full rationale.
'kafka_stream' (an external system pushing messages directly) is
explicitly out of scope for Phase 4 — see
docs/PHASE_4_IMPLEMENTATION_PLAN.md's completion notes.
"""
import json
import logging

from aiokafka import AIOKafkaConsumer

from .batch_worker import process_document
from .kafka_config import kafka_client_kwargs

log = logging.getLogger(__name__)


def _consumer_kwargs() -> dict:
    return {
        **kafka_client_kwargs(),
        "group_id": "pvh-ingestion-workers",
        "auto_offset_reset": "earliest",
        "enable_auto_commit": False,
    }


async def run_stream_consumer() -> None:
    consumer = AIOKafkaConsumer("doc-ingest", **_consumer_kwargs())
    await consumer.start()
    log.info("stream consumer started on topic doc-ingest")
    try:
        async for msg in consumer:
            try:
                job = json.loads(msg.value)
                process_document.apply_async(
                    kwargs={
                        "doc_id": job["doc_id"],
                        "tenant_id": job["tenant_id"],
                        "job_id": job["job_id"],
                        "r2_uri": job["source"]["r2_uri"],
                        "document_type": job.get("document_type", "clinical_note"),
                        "chunk_size": job.get("chunk_size", 512),
                        "chunk_overlap": job.get("chunk_overlap", 50),
                    },
                    queue="doc-ingest",
                )
                await consumer.commit()   # only commit after successful dispatch
            except Exception as exc:
                log.error("dispatch failed at offset=%d: %s", msg.offset, exc)
                # no commit -> Kafka redelivers this message to the group
    finally:
        await consumer.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_stream_consumer())
