"""
Kafka DLQ producer — the piece the reference docs (21, 24) sketched a
consumer/runbook around but never actually wired up. See
docs/PHASE_4_IMPLEMENTATION_PLAN.md §6 for the gap this closes.

Two entry points:
  - publish_to_dlq()      async, for use from stream_consumer.py (already
                           inside an asyncio event loop)
  - publish_to_dlq_sync() sync wrapper, for use from batch_worker.py's
                           Celery task (plain thread, no running loop)
"""
import asyncio
import json
import logging
import time
import uuid

from aiokafka import AIOKafkaProducer

from .kafka_config import kafka_client_kwargs

log = logging.getLogger(__name__)


async def publish_to_dlq(payload: dict, error: str) -> None:
    producer = AIOKafkaProducer(**kafka_client_kwargs())
    await producer.start()
    try:
        message = {
            **payload,
            "error": error[:2000],
            "failed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "correlation_id": str(uuid.uuid4()),
        }
        await producer.send_and_wait(
            topic="doc-dlq",
            key=str(payload.get("tenant_id", "")).encode(),
            value=json.dumps(message).encode(),
        )
        log.warning("published to doc-dlq: doc_id=%s error=%s", payload.get("doc_id"), error)
    finally:
        await producer.stop()


def publish_to_dlq_sync(payload: dict, error: str) -> None:
    """Sync wrapper for Celery task context (no running event loop)."""
    asyncio.run(publish_to_dlq(payload, error))
