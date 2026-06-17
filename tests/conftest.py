"""
Shared pytest fixtures for all test layers.
Phase 1: base fixtures and stubs.
Subsequent phases add DB session, mock Weaviate, mock Vault, etc.
"""
import asyncio
import os
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

# ── Event loop (required for pytest-asyncio) ──────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Test constants ─────────────────────────────────────────────────────────────
TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"

# Fake JWT payloads — replaced with real Keycloak tokens in Phase 3
ENGINEER_PAYLOAD = {
    "sub":          str(uuid.uuid5(uuid.NAMESPACE_DNS, "engineer@tenant1.test")),
    "email":        "engineer@tenant1.test",
    "tenant_id":    TENANT_A,
    "realm_access": {"roles": ["engineer"]},
}
ANALYST_PAYLOAD = {
    "sub":          str(uuid.uuid5(uuid.NAMESPACE_DNS, "analyst@tenant1.test")),
    "email":        "analyst@tenant1.test",
    "tenant_id":    TENANT_A,
    "realm_access": {"roles": ["analyst"]},
}
ADMIN_PAYLOAD = {
    "sub":          str(uuid.uuid5(uuid.NAMESPACE_DNS, "admin@tenant1.test")),
    "email":        "admin@tenant1.test",
    "tenant_id":    TENANT_A,
    "realm_access": {"roles": ["admin"]},
}
OTHER_TENANT_PAYLOAD = {
    "sub":          str(uuid.uuid5(uuid.NAMESPACE_DNS, "engineer@tenant2.test")),
    "email":        "engineer@tenant2.test",
    "tenant_id":    TENANT_B,
    "realm_access": {"roles": ["engineer"]},
}


# ── Mock Weaviate store ────────────────────────────────────────────────────────
@pytest.fixture
def mock_weaviate():
    """Fake WeaviateStore returning deterministic search results."""
    store = MagicMock()
    store.search = AsyncMock(return_value=[
        MagicMock(
            doc_id="d-001",
            chunk_text="Patient HbA1c 8.4% elevated — type 2 DM.",
            score=0.95,
            document_type="lab_result",
            metadata={},
        ),
        MagicMock(
            doc_id="d-002",
            chunk_text="Prescribed metformin 1000mg twice daily.",
            score=0.88,
            document_type="prescription",
            metadata={},
        ),
    ])
    store.upsert      = AsyncMock(return_value=None)
    store.delete      = AsyncMock(return_value=None)
    store.health_check = AsyncMock(return_value=True)
    return store


# ── Mock Vault client ─────────────────────────────────────────────────────────
@pytest.fixture
def mock_vault():
    """Fake HashiCorp Vault client."""
    vault = MagicMock()
    vault.secrets.kv.v2.read_secret_version = MagicMock(return_value={
        "data": {"data": {"api_key": "sk-test-key"}}
    })
    vault.secrets.transit.encrypt_data = MagicMock(return_value={
        "data": {"ciphertext": "vault:v1:TEST_CIPHERTEXT"}
    })
    vault.secrets.transit.decrypt_data = MagicMock(return_value={
        "data": {"plaintext": "dGVzdC1tcm4="}  # base64("test-mrn")
    })
    vault.sys.read_health_status = MagicMock(return_value={"initialized": True})
    return vault


# ── Mock LLM response ─────────────────────────────────────────────────────────
@pytest.fixture
def mock_llm():
    """Fake LLM router returning a canned answer."""
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value=(
            "Based on the retrieved records, the patient shows elevated "
            "HbA1c at 8.4% [1], consistent with type 2 diabetes management. "
            "Metformin 1000mg prescribed [2]."
        )
    )
    return llm


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
    """FastAPI app with mocked state for unit tests."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api-gateway"))
    from src.main import app

    app.state.vault    = mock_vault
    app.state.kafka    = mock_kafka
    app.state.db_pool  = None   # DB tests use their own session fixture
    return app


@pytest.fixture
def client(test_app):
    """Sync HTTPX test client."""
    from httpx import Client, ASGITransport
    with Client(transport=ASGITransport(app=test_app), base_url="http://testserver") as c:
        yield c


@pytest.fixture
def async_client(test_app):
    """Async HTTPX test client."""
    from httpx import AsyncClient, ASGITransport
    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    )
