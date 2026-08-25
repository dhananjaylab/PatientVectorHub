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

from ..observability import (
    kafka_consumer_lag,
    kafka_dispatch_failures_total,
    kafka_messages_consumed_total,
)
from .batch_worker import process_document
from .kafka_config import kafka_client_kwargs

log = logging.getLogger(__name__)

# Sampled every N successful dispatches rather than on every message --
# consumer.committed(partition) is a real network round trip to the
# broker (verified directly: inspected AIOKafkaConsumer.committed, it's
# an async method whose own docstring says "this call will block to do
# a remote call"), unlike highwater() which is cached from the last
# fetch response and free to call constantly. Doing this on every
# message would add a broker round trip to the hot path for a value
# that doesn't meaningfully change message-to-message anyway.
_LAG_SAMPLE_INTERVAL = 50


def _consumer_kwargs() -> dict:
    return {
        **kafka_client_kwargs(),
        "group_id": "pvh-ingestion-workers",
        "auto_offset_reset": "earliest",
        "enable_auto_commit": False,
    }


async def _sample_consumer_lag(consumer: AIOKafkaConsumer) -> None:
    """Updates pvh_kafka_consumer_lag{topic,partition} for every
    currently-assigned partition. highwater() is a free, cached read
    (no network call — see module-level comment on _LAG_SAMPLE_INTERVAL);
    committed() is the one real broker round trip in this function, done
    once per assigned partition, not once per message.

    Lag is defined here as highwater - committed_offset (how far the
    group's last SUCCESSFUL, durably-committed read is behind the log
    head) rather than highwater - position (the in-memory fetch
    cursor, which can be ahead of what's actually been durably
    processed) — matches this consumer's own manual-commit-after-
    successful-dispatch design (see module docstring above): committed
    offset is the only number that actually reflects "fully dispatched
    to Celery", which is what an operator paging on this metric cares
    about, not "already downloaded from Kafka but not yet acted on".
    """
    for tp in consumer.assignment():
        try:
            highwater = consumer.highwater(tp)
            committed = await consumer.committed(tp)
            if highwater is None or committed is None:
                continue
            kafka_consumer_lag.labels(topic=tp.topic, partition=str(tp.partition)).set(
                max(0, highwater - committed)
            )
        except Exception as e:  # noqa: BLE001 - a lag-sampling hiccup must never crash the consumer
            log.warning("Failed to sample consumer lag for %s: %s", tp, e)


async def run_stream_consumer() -> None:
    consumer = AIOKafkaConsumer("doc-ingest", **_consumer_kwargs())
    await consumer.start()
    log.info("stream consumer started on topic doc-ingest")
    dispatched_since_last_sample = 0
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
                kafka_messages_consumed_total.labels(topic=msg.topic).inc()

                dispatched_since_last_sample += 1
                if dispatched_since_last_sample >= _LAG_SAMPLE_INTERVAL:
                    await _sample_consumer_lag(consumer)
                    dispatched_since_last_sample = 0
            except Exception as exc:
                log.error("dispatch failed at offset=%d: %s", msg.offset, exc)
                kafka_dispatch_failures_total.labels(topic=msg.topic).inc()
                # no commit -> Kafka redelivers this message to the group
    finally:
        await consumer.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_stream_consumer())
