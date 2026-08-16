"""
Pytest fixtures for api-gateway service tests.

Provides:
- FastAPI app with mocked dependencies
- Test client (sync and async)
- Mock auth credentials
- Mock vault
- Mock kafka

Phase 8 addition: an autouse fixture that disables the process-wide rate
limiter singleton (middleware/rate_limit.py) for every test. See that
fixture's own docstring for why this has to be session-safe (the
singleton and its storage backend persist across every test in the run,
not per-test-app) rather than something each test file re-derives.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Event loop (required for pytest-asyncio) ──────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Rate limiter (Phase 8) ──────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _disable_rate_limiting():
    """The module-level `limiter` singleton (middleware/rate_limit.py) is
    shared process-wide, including across every test in this suite. Real
    routes (ingest.py, query.py, admin.py, audit.py) are decorated with
    @limiter.limit(...) at IMPORT time, so their rate-limit buckets
    persist for the lifetime of the pytest process, not per-test or
    per-app-instance. Without this, tests that call the same tightly
    limited route repeatedly across many test functions in one run (e.g.
    admin.py's create_key/revoke_key at 20/minute) would eventually start
    failing with unrelated 429s purely from test-suite volume, not from
    anything the test itself is checking.

    Verified directly (Phase 8 sandbox notes): `enabled=False` fully
    bypasses checking without even incrementing the underlying counter,
    and flipping back to True later resumes counting from whatever was
    already stored — so this must be set for the whole test run, not
    toggled per test. tests/unit/test_rate_limit.py deliberately
    re-enables the real flag for its own isolated toy routes/limiter
    instances to verify actual enforcement, and restores False
    afterward.
    """
    from src.middleware.rate_limit import limiter

    original = limiter.enabled
    limiter.enabled = False
    yield
    limiter.enabled = original


# ── Test constants ─────────────────────────────────────────────────────────────
TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"

# Fake JWT payloads
ENGINEER_PAYLOAD = {
    "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, "engineer@tenant1.test")),
    "email": "engineer@tenant1.test",
    "tenant_id": TENANT_A,
    "realm_access": {"roles": ["engineer"]},
}
ANALYST_PAYLOAD = {
    "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, "analyst@tenant1.test")),
    "email": "analyst@tenant1.test",
    "tenant_id": TENANT_A,
    "realm_access": {"roles": ["analyst"]},
}
ADMIN_PAYLOAD = {
    "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, "admin@tenant1.test")),
    "email": "admin@tenant1.test",
    "tenant_id": TENANT_A,
    "realm_access": {"roles": ["admin"]},
}
OTHER_TENANT_PAYLOAD = {
    "sub": str(uuid.uuid5(uuid.NAMESPACE_DNS, "engineer@tenant2.test")),
    "email": "engineer@tenant2.test",
    "tenant_id": TENANT_B,
    "realm_access": {"roles": ["engineer"]},
}


# ── Mock Vault client ─────────────────────────────────────────────────────────
@pytest.fixture
def mock_vault():
    """Fake HashiCorp Vault client."""
    vault = MagicMock()
    vault.secrets.kv.v2.read_secret_version = MagicMock(
        return_value={"data": {"data": {"api_key": "sk-test-key"}}}
    )
    vault.secrets.transit.encrypt_data = MagicMock(
        return_value={"data": {"ciphertext": "vault:v1:TEST_CIPHERTEXT"}}
    )
    vault.secrets.transit.decrypt_data = MagicMock(
        return_value={
            "data": {"plaintext": "dGVzdC1tcm4="}  # base64("test-mrn")
        }
    )
    vault.sys.read_health_status = MagicMock(return_value={"initialized": True})
    return vault


# ── Mock Kafka producer ───────────────────────────────────────────────────────
@pytest.fixture
def mock_kafka():
    """Fake AIOKafka producer."""
    kafka = AsyncMock()
    kafka.send_and_wait = AsyncMock(return_value=None)
    return kafka


# ── FastAPI test client ───────────────────────────────────────────────────────
@pytest.fixture
def test_app(mock_vault, mock_kafka):
    """FastAPI app with mocked state for unit tests.

    Patches AIOKafkaProducer so the lifespan handler never attempts a real
    Kafka connection, and patches asyncpg.create_pool so the DB readiness
    pool doesn't need a running Postgres instance.
    """
    import os
    import ssl
    import sys
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_producer = AsyncMock()
    mock_producer.start = AsyncMock()
    mock_producer.stop = AsyncMock()
    mock_producer.send_and_wait = AsyncMock()

    mock_db_pool = AsyncMock()
    mock_db_pool.close = AsyncMock()
    mock_db_pool.fetchval = AsyncMock(return_value=1)

    # Mock SSL context creation to avoid file loading during tests
    mock_ssl_context = MagicMock(spec=ssl.SSLContext)

    # Patch AIOKafkaProducer, asyncpg.create_pool, and create_ssl_context
    # to prevent real infrastructure connections during tests
    with patch("src.main.AIOKafkaProducer", return_value=mock_producer), \
         patch("asyncpg.create_pool", return_value=mock_db_pool), \
         patch("aiokafka.helpers.create_ssl_context", return_value=mock_ssl_context):
        from src.main import app

        app.state.vault = mock_vault
        app.state.kafka = mock_producer
        app.state.db_pool = mock_db_pool
        yield app


@pytest.fixture
def client(test_app):
    """Sync TestClient."""
    from fastapi.testclient import TestClient

    with TestClient(test_app, base_url="http://testserver") as c:
        yield c


@pytest.fixture
def async_client(test_app):
    """Async HTTPX test client."""
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    )
