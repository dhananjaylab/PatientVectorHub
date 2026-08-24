"""
PatientVectorHub — ingestion worker metrics + tracing (Phase 10 / ADR-017).

Three separate long-running processes here, none of them FastAPI, none
of them with an HTTP server of their own: celery-worker, celery-beat,
kafka-consumer (stream_consumer.py's own asyncio loop). Each needs its
own bare metrics port -- see config.py's CELERY_WORKER_METRICS_PORT /
KAFKA_CONSUMER_METRICS_PORT / CELERY_BEAT_METRICS_PORT.

celery-worker is NOT single-process. docker-compose.yml runs it with
`-c 4` -- Celery's default prefork pool, meaning 4 forked CHILD
processes actually execute tasks, while a separate PARENT process
supervises them. A Counter incremented inside a task (child process
memory) is invisible to an HTTP server naively started in that same
child (each child would only ever report its own 1/4 of traffic) or in
the parent (which never executes tasks itself, so it would report zero).

Verified directly (inspected prometheus_client.values source, not
assumed): the library decides ONCE, at first import of
`prometheus_client.values`, whether to use its plain in-memory
MutexValue or its mmap-backed MultiProcessValue -- via a module-level
`ValueClass = get_value_class()` that reads PROMETHEUS_MULTIPROC_DIR
from os.environ AT THAT IMPORT MOMENT. This means the env var must be
set on the container/process BEFORE the Python interpreter even starts
importing this module -- setting it from inside worker_process_init()
below would already be too late, since celery_app.py's bottom-of-file
`from . import batch_worker` (which imports this module, which imports
`prometheus_client`) has by definition already run by the time any
Celery signal fires. docker-compose.yml's celery-worker service sets
PROMETHEUS_MULTIPROC_DIR as a real container environment variable for
exactly this reason, with a clean-directory step ahead of `celery
worker` in that service's command (stale .db files from a previous
container's run would silently corrupt aggregation otherwise -- this is
prometheus_client's own documented multiprocess caveat, not specific to
this codebase).

celery-beat and kafka-consumer are both genuinely single-process (beat
never forks; stream_consumer.py is one asyncio event loop) -- multiprocess
mode would be harmless but pointless machinery for either, so both use
the plain default registry via start_worker_metrics_server() below.
"""
from __future__ import annotations

import logging
import os

from prometheus_client import Counter, Gauge, Histogram

from .config import settings

log = logging.getLogger(__name__)

# ── Metric definitions ───────────────────────────────────────────────────────
documents_processed_total = Counter(
    "pvh_documents_processed_total",
    "Total documents fully processed by ingestion workers (parse+chunk+embed+upsert)",
    ["status", "document_type"],
)
document_processing_duration_seconds = Histogram(
    "pvh_document_processing_duration_seconds",
    "End-to-end per-document processing duration in seconds",
    ["document_type"],
)
dlq_messages_total = Counter(
    "pvh_dlq_messages_total",
    "Total messages published to the ingestion dead-letter queue",
    ["reason"],
)
kafka_consumer_lag = Gauge(
    "pvh_kafka_consumer_lag",
    "Messages behind the high watermark, by topic and partition",
    ["topic", "partition"],
)
kafka_messages_consumed_total = Counter(
    "pvh_kafka_messages_consumed_total",
    "Total Kafka messages successfully dispatched by the stream consumer",
    ["topic"],
)
kafka_dispatch_failures_total = Counter(
    "pvh_kafka_dispatch_failures_total",
    "Total Kafka messages that failed dispatch (before any DLQ routing)",
    ["topic"],
)
scheduled_task_duration_seconds = Histogram(
    "pvh_scheduled_task_duration_seconds",
    "Celery-beat scheduled task duration in seconds",
    ["task_name"],
)
scheduled_task_runs_total = Counter(
    "pvh_scheduled_task_runs_total",
    "Total celery-beat scheduled task runs",
    ["task_name", "status"],
)


def start_worker_metrics_server(port: int) -> None:
    """For genuinely single-process services (celery-beat,
    kafka-consumer) -- plain default registry, no multiprocess
    machinery needed. No-op when METRICS_ENABLED is False."""
    if not settings.METRICS_ENABLED:
        return
    from prometheus_client import start_http_server

    start_http_server(port)
    log.info("Metrics server started", extra={"port": port})


def celery_worker_init(**_kwargs) -> None:
    """Bind to celery.signals.worker_init -- fires ONCE in the PARENT
    process, before any child is forked. Starts the aggregating HTTP
    server using MultiProcessCollector, which reads every child's
    individual .db files out of PROMETHEUS_MULTIPROC_DIR. Requires that
    directory to already exist and be writable (docker-compose.yml's
    celery-worker command creates + clears it before `celery worker`
    itself starts) -- MultiProcessCollector raises ValueError outright
    if the directory doesn't exist, by design (see observability.py's
    module docstring in api-gateway for the identical check, verified
    the same way there: inspected the library's own source directly).
    """
    if not settings.METRICS_ENABLED:
        return
    multiproc_dir = settings.PROMETHEUS_MULTIPROC_DIR or os.environ.get(
        "PROMETHEUS_MULTIPROC_DIR"
    )
    if not multiproc_dir:
        log.warning(
            "celery-worker started with no PROMETHEUS_MULTIPROC_DIR set -- "
            "per-child metrics will NOT be aggregated correctly under a "
            "prefork pool with concurrency > 1. Falling back to a plain "
            "single-process server, which will only ever reflect whichever "
            "one child happened to handle the most recent scrape."
        )
        start_worker_metrics_server(settings.CELERY_WORKER_METRICS_PORT)
        return

    from threading import Thread
    from wsgiref.simple_server import make_server

    from prometheus_client import CollectorRegistry, make_wsgi_app, multiprocess

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry, path=multiproc_dir)
    app = make_wsgi_app(registry)

    server = make_server("0.0.0.0", settings.CELERY_WORKER_METRICS_PORT, app)
    Thread(target=server.serve_forever, daemon=True).start()
    log.info(
        "Aggregating metrics server started (multiprocess mode)",
        extra={"port": settings.CELERY_WORKER_METRICS_PORT, "multiproc_dir": multiproc_dir},
    )


def celery_worker_process_shutdown(**_kwargs) -> None:
    """Bind to celery.signals.worker_process_shutdown -- fires in each
    CHILD process as it exits. Cleans up that child's per-PID .db files
    so PROMETHEUS_MULTIPROC_DIR doesn't accumulate dead entries across a
    long-running worker's normal child recycling (Celery periodically
    restarts child processes even in steady state, per
    worker_max_tasks_per_child-style rotation)."""
    multiproc_dir = settings.PROMETHEUS_MULTIPROC_DIR or os.environ.get(
        "PROMETHEUS_MULTIPROC_DIR"
    )
    if not multiproc_dir:
        return
    from prometheus_client import multiprocess

    multiprocess.mark_process_dead(os.getpid(), path=multiproc_dir)


# ── OpenTelemetry tracing ────────────────────────────────────────────────────
_tracing_configured = False


def configure_tracing() -> None:
    """No FastAPI app to instrument here (unlike api-gateway's
    observability.py) -- CeleryInstrumentor patches Celery's own task
    dispatch machinery directly rather than wrapping an ASGI app. No-op
    when TRACING_ENABLED is False, matching api-gateway's identical
    posture."""
    global _tracing_configured
    if not settings.TRACING_ENABLED:
        log.info("Tracing disabled (TRACING_ENABLED=false)")
        return
    if _tracing_configured:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": "1.0.0",
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=settings.JAEGER_ENDPOINT,
        insecure=settings.ENVIRONMENT != "production",
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    CeleryInstrumentor().instrument()

    from .db.session import get_engine

    SQLAlchemyInstrumentor().instrument(engine=get_engine())

    _tracing_configured = True
    log.info("Tracing configured", extra={"jaeger_endpoint": settings.JAEGER_ENDPOINT})


def reset_tracing_state_for_tests() -> None:
    """Test-only escape hatch -- same caveat as api-gateway's
    observability.py twin: resets this module's own latch, not
    OpenTelemetry's own process-wide singletons."""
    global _tracing_configured
    _tracing_configured = False
