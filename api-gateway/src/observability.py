"""
PatientVectorHub — Prometheus metrics + OpenTelemetry tracing (Phase 10 /
ADR-017).

Hand-rolled metrics via the raw `prometheus_client` API rather than
`prometheus-fastapi-instrumentator` -- matches this codebase's own
established preference for a few explicit lines over an extra dependency
(logging_config.py hand-rolls its JSON formatter instead of
python-json-logger; middleware/rate_limit.py's whole ADR-015 rationale is
picking in-process code over a new component). The `/metrics` route
itself was already whitelisted in middleware/auth.py's public_paths
before this phase existed, so this only had to build the thing that
belongs there.

Multiprocess footgun (real, easy to miss): prometheus_client's default
CollectorRegistry silently produces PER-PROCESS, not aggregated, numbers
when uvicorn/gunicorn run with more than one worker -- every `/metrics`
scrape would only ever see whichever single worker happened to handle
it. settings.PROMETHEUS_MULTIPROC_DIR (empty by default, matching single-
process local dev where the default registry is correct) switches
metrics_endpoint() over to prometheus_client.multiprocess.
MultiProcessCollector, which aggregates every worker's counters from
files in that directory. Verified against the installed library
directly (inspected MultiProcessCollector.__init__'s actual source, not
assumed from docs) that it reads the PROMETHEUS_MULTIPROC_DIR env var by
that exact name -- config.py's setting is named to match exactly, not
translated through another name.

Jaeger v1 (jaegertracing/all-in-one:1.x) reached end-of-life
2025-12-31; docker-compose.yml now runs Jaeger v2, which speaks OTLP
natively on the same 4317 gRPC port JAEGER_ENDPOINT already pointed at
before this phase existed -- no code here had to change to account for
that, only the compose file's image tag.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram
from prometheus_client import generate_latest as _generate_latest

from .config import settings

log = logging.getLogger(__name__)

# ── Prometheus metric definitions ──────────────────────────────────────────
# Module-level singletons, like middleware/rate_limit.py's `limiter` --
# every router imports these same instances so counts aren't silently
# split across separately-constructed Counter objects.
http_requests_total = Counter(
    "pvh_http_requests_total",
    "Total HTTP requests handled by the API gateway",
    ["method", "route", "status_code"],
)
http_request_duration_seconds = Histogram(
    "pvh_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
)
query_latency_seconds = Histogram(
    "pvh_query_latency_seconds",
    "RAG query end-to-end latency in seconds, by LLM provider",
    ["llm_provider"],
)
documents_ingested_total = Counter(
    "pvh_documents_ingested_total",
    "Total documents submitted for ingestion",
    ["status", "document_type", "source_type"],
)
rate_limit_rejections_total = Counter(
    "pvh_rate_limit_rejections_total",
    "Total requests rejected by the in-process rate limiter",
    ["route"],
)
audit_log_writes_total = Counter(
    "pvh_audit_log_writes_total",
    "Total audit_logs rows written, by action",
    ["action"],
)
vault_operations_total = Counter(
    "pvh_vault_operations_total",
    "Total Vault Transit operations, by operation and outcome",
    ["operation", "status"],
)


def _resolve_registry() -> CollectorRegistry | None:
    """Returns the multiprocess-aggregating registry when
    PROMETHEUS_MULTIPROC_DIR is set, else None (generate_latest's own
    default: the global REGISTRY every Counter/Histogram above already
    registered themselves into at import time)."""
    multiproc_dir = settings.PROMETHEUS_MULTIPROC_DIR
    if not multiproc_dir:
        return None
    if not os.path.isdir(multiproc_dir):
        log.warning(
            "PROMETHEUS_MULTIPROC_DIR=%s does not exist -- falling back to the "
            "single-process registry, which will produce per-worker-only numbers "
            "if API_WORKERS > 1.",
            multiproc_dir,
        )
        return None
    from prometheus_client import multiprocess

    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return registry


async def metrics_endpoint() -> Response:
    """Handler for GET /metrics -- registered in main.py's create_app()
    only when settings.METRICS_ENABLED is True, matching
    RATE_LIMIT_ENABLED's "declared, not implied" precedent."""
    registry = _resolve_registry()
    body = _generate_latest(registry) if registry is not None else _generate_latest()
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)


async def metrics_middleware(request, call_next):
    """Records pvh_http_requests_total / pvh_http_request_duration_seconds
    for every request. Uses the matched route's path template
    (request.scope["route"].path, e.g. "/v1/ingest/jobs/{job_id}"), not
    the raw request.url.path -- the raw path would blow up cardinality
    with one label value per distinct job_id/patient_id ever requested,
    which is exactly the kind of thing that quietly makes a Prometheus
    instance fall over. Falls back to the raw path only for genuinely
    unmatched routes (404s), where there is no template to use.
    """
    import time

    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    route = request.scope.get("route")
    route_path = route.path if route is not None else request.url.path

    http_requests_total.labels(
        method=request.method, route=route_path, status_code=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(method=request.method, route=route_path).observe(
        duration
    )
    return response


# ── OpenTelemetry tracing ────────────────────────────────────────────────────
_tracing_configured = False


def configure_tracing(app: FastAPI) -> None:
    """Called once from main.py's create_app(), mirroring
    logging_config.configure_logging()'s "called once at startup, not
    per-request" shape. No-op (and does not import the otel packages at
    all) when settings.TRACING_ENABLED is False, so a local dev machine
    with no Jaeger running never pays even an import cost for this.
    """
    global _tracing_configured
    if not settings.TRACING_ENABLED:
        log.info("Tracing disabled (TRACING_ENABLED=false)")
        return
    if _tracing_configured:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
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
        insecure=not settings.is_production,
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # excluded_urls keeps liveness/readiness/scrape traffic out of Jaeger --
    # every probe hitting these on a ~10s interval would otherwise dwarf
    # actual request traces with pure noise.
    FastAPIInstrumentor.instrument_app(
        app, excluded_urls="/health,/ready,/metrics"
    )

    from .db.session import get_engine

    SQLAlchemyInstrumentor().instrument(engine=get_engine().sync_engine)

    _tracing_configured = True
    log.info("Tracing configured", extra={"jaeger_endpoint": settings.JAEGER_ENDPOINT})


def reset_tracing_state_for_tests() -> None:
    """Test-only escape hatch: resets this module's own latch so
    configure_tracing() will attempt to run again in the same process.
    Does NOT reset the OpenTelemetry SDK's own global state -- verified
    directly: `trace.set_tracer_provider()` and
    SQLAlchemyInstrumentor().instrument() on the same engine both log a
    (non-fatal) "already instrumented"-style warning on a second real
    call within one process, because those are OTel's own process-wide
    singletons, not something this module tracks or controls. In real
    usage this is a non-issue -- main.py's create_app() calls
    configure_tracing() exactly once per running process. This exists so
    a test can assert configure_tracing() is callable and doesn't raise,
    not to get a second fully-clean trace pipeline in one process."""
    global _tracing_configured
    _tracing_configured = False
