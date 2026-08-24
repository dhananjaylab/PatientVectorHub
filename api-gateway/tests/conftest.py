"""Shared pytest fixtures for api-gateway unit tests.

RECONSTRUCTED (Phase 10 prep): this file came through as "[Binary file]"
(unreadable) in the repo dump -- same failure mode documented in
ingestion/requirements.txt's own docstring for that file, once before.
Reconstructed from every test file's actual fixture usage (AST-inspected
across tests/unit/*.py: only `test_app` and `client` are pulled from
here -- test_query_router.py deliberately builds its own standalone app
instead, per its own docstring, precisely to avoid this fixture's app
touching rag_engine's import chain) plus src/main.py's
create_app()/lifespan() and src/routers/health.py's defensive
getattr(app_state, ...) handling.

Key inference, not a guess: main.py's lifespan awaits
AIOKafkaProducer.start() unconditionally (no try/except, unlike
db_pool's graceful-degradation wrapper) -- a fixture that entered the
lifespan via `with TestClient(app) as client:` would hang/fail against
this sandbox's nonexistent broker. /health touches no app.state at all
and /ready already treats an absent db_pool/vault/kafka as
"not_initialized" rather than crashing, so building the app WITHOUT
running its lifespan is not just convenient but is what the rest of
this codebase's own code already assumes a unit-test context looks
like. Please diff this against your real tests/conftest.py and
reconcile before relying on it beyond Phase 10's own new tests.
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh_test"
)
os.environ.setdefault(
    "DATABASE_URL_SYNC", "postgresql+psycopg2://pvh:pvh_local@localhost:5432/pvh_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("VAULT_ADDR", "http://localhost:8200")
os.environ.setdefault("VAULT_TOKEN", "test-token")
os.environ.setdefault("JAEGER_ENDPOINT", "http://localhost:4317")


@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """Process-wide default: the shared middleware.rate_limit.limiter
    singleton stays disabled for every test in this suite unless a test
    explicitly re-enables it around just itself -- see
    tests/unit/test_rate_limit.py's TestRateLimitEnforcement, whose own
    docstring names this exact fixture and which saves/restores
    limiter.enabled itself rather than relying on this fixture's
    teardown. Without this, any router test that happens to hit a
    @limiter.limit(...)-decorated route more than a handful of times
    would start seeing real 429s that have nothing to do with what it's
    testing."""
    from src.middleware.rate_limit import limiter

    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original


@pytest.fixture()
def test_app():
    """The real FastAPI app via create_app(), NOT run through its
    lifespan -- see module docstring for why that's correct here, not
    just expedient."""
    from src.main import create_app

    return create_app()


@pytest.fixture()
def client(test_app):
    """Sync TestClient WITHOUT entering the lifespan context manager --
    deliberately avoids AIOKafkaProducer.start(), matching
    test_query_router.py's own documented reason for isolating
    router-level tests from main.py's full lifespan."""
    return TestClient(test_app)
