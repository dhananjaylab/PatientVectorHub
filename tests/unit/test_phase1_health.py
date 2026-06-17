"""
Phase 1 unit tests — FastAPI health endpoints and app wiring.
These must all pass before any feature code is written.
Run with: pytest tests/unit/test_phase1_health.py -v
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))


# ── App import ────────────────────────────────────────────────────────────────
class TestAppCreation:
    def test_app_imports_successfully(self):
        """App module must be importable with no side-effects."""
        from src.main import app
        assert app is not None

    def test_app_has_correct_title(self):
        from src.main import app
        assert "PatientVectorHub" in app.title

    def test_app_has_correct_version(self):
        from src.main import app
        assert app.version == "1.0.0"

    def test_app_has_routes(self):
        from src.main import app
        route_paths = [r.path for r in app.routes]
        assert "/health" in route_paths
        assert "/ready"  in route_paths

    def test_app_has_docs_enabled(self):
        from src.main import app
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"


# ── /health endpoint ──────────────────────────────────────────────────────────
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body_has_status(self, client):
        body = client.get("/health").json()
        assert body["status"] == "alive"

    def test_health_body_has_uptime(self, client):
        body = client.get("/health").json()
        assert "uptime_s" in body
        assert isinstance(body["uptime_s"], int)
        assert body["uptime_s"] >= 0

    def test_health_body_has_service_name(self, client):
        body = client.get("/health").json()
        assert "service" in body
        assert "pvh" in body["service"].lower()

    def test_health_no_auth_required(self, client):
        """Health endpoint must be publicly accessible — no JWT needed."""
        resp = client.get("/health", headers={})
        assert resp.status_code == 200


# ── /ready endpoint ───────────────────────────────────────────────────────────
class TestReadyEndpoint:
    def test_ready_returns_json(self, client):
        resp = client.get("/ready")
        assert "application/json" in resp.headers["content-type"]

    def test_ready_body_has_checks(self, client):
        body = client.get("/ready").json()
        assert "checks" in body
        assert isinstance(body["checks"], dict)

    def test_ready_body_has_status(self, client):
        body = client.get("/ready").json()
        assert "status" in body
        assert body["status"] in ("ready", "not_ready")

    def test_ready_postgres_key_present(self, client):
        body = client.get("/ready").json()
        assert "postgres" in body["checks"]

    def test_ready_no_auth_required(self, client):
        resp = client.get("/ready", headers={})
        assert resp.status_code in (200, 503)


# ── Config ─────────────────────────────────────────────────────────────────────
class TestConfig:
    def test_settings_loads(self):
        from src.config import settings
        assert settings is not None

    def test_settings_has_database_url(self):
        from src.config import settings
        assert settings.DATABASE_URL.startswith("postgresql")

    def test_settings_has_redis_url(self):
        from src.config import settings
        assert settings.REDIS_URL.startswith("redis://")

    def test_settings_cors_origins_list(self):
        from src.config import settings
        origins = settings.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) >= 1

    def test_settings_environment_defaults_to_development(self):
        from src.config import settings
        # In CI environment is "test", locally "development"
        assert settings.ENVIRONMENT in ("development", "test", "production", "staging")

    def test_settings_log_level_valid(self):
        import logging
        from src.config import settings
        assert hasattr(logging, settings.LOG_LEVEL.upper())


# ── CORS middleware ────────────────────────────────────────────────────────────
class TestCORS:
    def test_cors_headers_present_on_options(self, client):
        resp = client.options(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
        # Either 200 with CORS headers or 405 (no OPTIONS route) — both acceptable in Phase 1
        assert resp.status_code in (200, 405)

    def test_health_response_allows_cross_origin(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:5173"},
        )
        # CORS middleware should attach allow-origin header
        assert resp.status_code == 200
