"""
Unit tests for api-gateway/src/observability.py (Phase 10 / ADR-017).
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from src import observability


@pytest.fixture(autouse=True)
def _reset_tracing_latch():
    observability.reset_tracing_state_for_tests()
    yield
    observability.reset_tracing_state_for_tests()


class TestMetricsEndpoint:
    @pytest.mark.asyncio
    async def test_returns_prometheus_text_content_type(self):
        response = await observability.metrics_endpoint()
        assert response.media_type.startswith("text/plain")

    @pytest.mark.asyncio
    async def test_body_contains_registered_metric_names(self):
        observability.http_requests_total.labels(
            method="GET", route="/health", status_code="200"
        ).inc()
        response = await observability.metrics_endpoint()
        body = response.body.decode()
        assert "pvh_http_requests_total" in body

    @pytest.mark.asyncio
    async def test_falls_back_to_default_registry_when_multiproc_dir_unset(self):
        with patch.object(observability.settings, "PROMETHEUS_MULTIPROC_DIR", ""):
            response = await observability.metrics_endpoint()
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_falls_back_to_default_registry_when_multiproc_dir_missing_on_disk(self):
        """A misconfigured (nonexistent) directory must degrade to the
        single-process registry rather than raise -- an ops mistake in
        an env var shouldn't take /metrics itself down."""
        with patch.object(
            observability.settings, "PROMETHEUS_MULTIPROC_DIR", "/nonexistent/path/xyz"
        ):
            response = await observability.metrics_endpoint()
        assert response.status_code == 200


class TestMetricsMiddleware:
    @pytest.mark.asyncio
    async def test_records_request_count_and_duration_using_route_template(self):
        """Must use the matched route TEMPLATE ("/v1/x/{id}"), not the
        raw path with the real id interpolated in -- using the raw path
        would blow up label cardinality with one series per id ever
        requested."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/ingest/jobs/abc-123"
        fake_route = MagicMock()
        fake_route.path = "/v1/ingest/jobs/{job_id}"
        request.scope = {"route": fake_route}

        response = MagicMock()
        response.status_code = 200

        async def call_next(_req):
            return response

        before = observability.http_requests_total.labels(
            method="GET", route="/v1/ingest/jobs/{job_id}", status_code="200"
        )._value.get()

        result = await observability.metrics_middleware(request, call_next)

        after = observability.http_requests_total.labels(
            method="GET", route="/v1/ingest/jobs/{job_id}", status_code="200"
        )._value.get()

        assert result is response
        assert after == before + 1

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_path_when_route_is_unmatched(self):
        """404s have no matched route -- scope["route"] is absent, and
        this must not raise."""
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/totally/unknown/path"
        request.scope = {}

        response = MagicMock()
        response.status_code = 404

        async def call_next(_req):
            return response

        result = await observability.metrics_middleware(request, call_next)
        assert result is response


class TestConfigureTracing:
    def test_noop_when_tracing_disabled(self):
        with patch.object(observability.settings, "TRACING_ENABLED", False):
            app = FastAPI()
            with patch(
                "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"
            ) as mock_instrument:
                observability.configure_tracing(app)
            mock_instrument.assert_not_called()
        assert observability._tracing_configured is False

    def test_configures_once_and_is_idempotent(self):
        app = FastAPI()
        observability.configure_tracing(app)
        assert observability._tracing_configured is True
        # second call on the same (already-configured) latch must not raise
        observability.configure_tracing(app)

    def test_excludes_health_ready_metrics_from_tracing(self):
        """excluded_urls keeps liveness/readiness/scrape noise out of
        Jaeger -- verified by inspecting the actual call args passed to
        FastAPIInstrumentor, not by asserting on trace output (which
        would need a live collector)."""
        app = FastAPI()
        with patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor.instrument_app"
        ) as mock_instrument:
            observability.configure_tracing(app)
        _, kwargs = mock_instrument.call_args
        assert "/health" in kwargs["excluded_urls"]
        assert "/ready" in kwargs["excluded_urls"]
        assert "/metrics" in kwargs["excluded_urls"]
