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
import threading
import time
import uuid

from aiokafka import AIOKafkaProducer

from ..observability import dlq_messages_total
from .kafka_config import kafka_client_kwargs

log = logging.getLogger(__name__)


async def publish_to_dlq(payload: dict, error: str, reason: str = "processing_failure") -> None:
    """`reason` is deliberately a small, caller-chosen bucket (e.g.
    "processing_failure", "parse_failure"), never the raw `error` string
    — using free-text error messages as a Prometheus label would blow up
    cardinality with one series per distinct exception message ever
    seen, the same trap observability.py's metrics_middleware avoids by
    using route templates instead of raw paths. Every current caller
    (batch_worker.py's one terminal-failure branch) uses the default —
    the underlying except block doesn't yet distinguish parse vs.
    embedding vs. store-upsert failures into separate reasons; a future
    caller can pass a more specific value once that distinction exists
    without any signature change needed here.
    """
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
        dlq_messages_total.labels(reason=reason).inc()
    finally:
        await producer.stop()


def publish_to_dlq_sync(payload: dict, error: str, reason: str = "processing_failure") -> None:
    """Run the async publisher from sync Celery task code.

    Celery normally invokes tasks without a running event loop, but eager
    execution from async integration tests can run the task on a thread that
    already owns one. In that case asyncio.run() cannot be used directly.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(publish_to_dlq(payload, error, reason=reason))
        return

    error_holder: list[BaseException] = []

    def run_in_thread() -> None:
        try:
            asyncio.run(publish_to_dlq(payload, error, reason=reason))
        except Exception as exc:  # propagate producer failures to Celery
            error_holder.append(exc)

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()
    if error_holder:
        raise error_holder[0]
