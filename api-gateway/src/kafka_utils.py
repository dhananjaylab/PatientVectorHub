"""
Kafka producer helpers for api-gateway.

publish_document_ingest() is called once PER DOCUMENT when a job is
created (see routers/ingest.py) — NOT once per job. This is a deliberate
Phase 4 design choice: doc-ingest has 12 partitions specifically so many
documents from the same job can be processed in parallel across worker
replicas; publishing a single job-level message (as doc 13/37's original
sketch did) would leave that partitioning unused and push document
discovery onto whichever single worker happened to consume it. See
ingestion/src/workers/stream_consumer.py's docstring for the consumer
side of this.
"""
import json
import uuid

from aiokafka import AIOKafkaProducer


async def publish_document_ingest(
    producer: AIOKafkaProducer,
    *,
    doc_id: str,
    job_id: str,
    tenant_id: str,
    source_path: str,
    document_type: str,
    embedding_model: str,
    chunk_size: int,
    chunk_overlap: int,
) -> None:
    payload = {
        "doc_id": doc_id,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "source": {"r2_uri": source_path},
        "document_type": document_type,
        "model": embedding_model,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "correlation_id": str(uuid.uuid4()),
    }
    await producer.send_and_wait(
        topic="doc-ingest",
        key=tenant_id.encode(),          # partition key = tenant -> ordered per tenant
        value=json.dumps(payload).encode(),
        headers=[(b"correlation-id", payload["correlation_id"].encode())],
    )
