"""
Shared pytest fixtures for all test layers.

Phase 7 additions:
  1. "rag-engine" added to subproject_names (new subproject).
  2. _ensure_cross_package_alias() — makes vector-store/src and
     rag-engine/src importable as the top-level `vector_store` /
     `rag_engine` package names, the same identifiers Docker's
     `COPY vector-store/src/ ./vector_store/`-style build steps produce.
     This is a previously-latent gap: every existing unit test that
     touches vector-store imports it via its OWN subproject's
     sys.path.insert()+`from src.X import Y` convention (see
     test_weaviate_search_delete.py, test_qdrant_store.py,
     test_dual_write_store.py) — none of them cross-imports `vector_store`
     from OUTSIDE that subproject. ingestion/src/workers/batch_worker.py
     does cross-import it, but has no dedicated unit test, so nothing
     ever exercised this at collection time before. Phase 7's
     rag-engine/src/retriever.py and synthesizer.py both do
     `from vector_store.interface import ...` at module level (their
     entire job is calling into vector_store), and
     api-gateway/src/routers/query.py does `from rag_engine.retriever
     import retrieve` the same way — so this is the first phase where a
     *unit* test actually needs the cross-import to resolve, not just a
     Docker-built integration environment. Without this, tests/unit/
     test_retriever.py, test_rag_synthesizer.py, and
     test_query_router.py would fail to *collect* (not just fail),
     which fails the entire pytest run — see MANUAL_INTEGRATION_NOTES.md
     for the local-dev / CI implications.
"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Event loop (required for pytest-asyncio) ──────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── Test constants ─────────────────────────────────────────────────────────────
TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"

# Fake JWT payloads — replaced with real Keycloak tokens in Phase 3
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


# ── Mock Weaviate store ────────────────────────────────────────────────────────
@pytest.fixture
def mock_weaviate():
    """Fake WeaviateStore returning deterministic search results."""
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
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
        ]
    )
    store.upsert = AsyncMock(return_value=None)
    store.delete = AsyncMock(return_value=None)
    store.health_check = AsyncMock(return_value=True)
    return store


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
    """FastAPI app with mocked state for unit tests.

    Patches AIOKafkaProducer so the lifespan handler never attempts a real
    Kafka connection, and patches asyncpg.create_pool so the DB readiness
    pool doesn't need a running Postgres instance.
    """
    import os
    import sys
    from unittest.mock import AsyncMock, patch

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api-gateway"))

    mock_producer = AsyncMock()
    mock_producer.start = AsyncMock()
    mock_producer.stop = AsyncMock()
    mock_producer.send_and_wait = AsyncMock()

    with patch("src.main.AIOKafkaProducer", return_value=mock_producer):
        from src.main import app

        app.state.vault = mock_vault
        app.state.db_pool = None
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


def _ensure_cross_package_alias(repo_root: str, dir_name: str, module_name: str) -> None:
    """Make <repo_root>/<dir_name>/src importable as top-level
    `module_name` — see this file's module docstring for why this
    exists. Idempotent (checks sys.modules first) and cheap, so it's
    safe to call unconditionally rather than only for test files that
    are known in advance to need it."""
    import importlib.util
    import sys

    if module_name in sys.modules:
        return
    src_dir = os.path.join(repo_root, dir_name, "src")
    init_path = os.path.join(src_dir, "__init__.py")
    if not os.path.isfile(init_path):
        return
    spec = importlib.util.spec_from_file_location(
        module_name, init_path, submodule_search_locations=[src_dir]
    )
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


def pytest_runtest_setup(item):
    """Clear cached 'src' modules AND fix sys.path so the correct subproject
    is the *only* one present before every test.

    Each test file does a module-level sys.path.insert(0, "<subproject>") that
    only fires once during collection. Without this hook, whichever subproject
    was inserted *last* during collection shadows all the others, and
    sys.modules caching makes it even worse when different test files share
    the 'src' package name across api-gateway, ingestion, rag-engine, and
    vector-store.

    Strategy:
    1. Flush every cached 'src' module from sys.modules.
    2. Remove all subproject roots from sys.path.
    3. Re-insert the *correct* subproject root for the current test file by
       reading its source for the `sys.path.insert(0, ...)` pattern.
    4. Register vector_store / rag_engine as top-level cross-package
       aliases (Phase 7 addition — see module docstring).
    """
    import os
    import sys

    # 1. Remove cached src modules
    for k in list(sys.modules.keys()):
        if k == "src" or k.startswith("src."):
            del sys.modules[k]

    # 2. Remove all subproject roots from sys.path
    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    subproject_names = ("api-gateway", "ingestion", "vector-store", "rag-engine")
    subproject_dirs = {os.path.normpath(os.path.join(repo_root, sp)) for sp in subproject_names}
    sys.path[:] = [p for p in sys.path if os.path.normpath(p) not in subproject_dirs]

    # 3. Re-insert the correct subproject for *this* test file.
    #    We inspect the test module's source for the sys.path.insert line
    #    that names the subproject (e.g., "api-gateway", "ingestion", etc.).
    test_file = str(item.fspath)
    try:
        with open(test_file, encoding="utf-8") as f:
            source = f.read(2048)  # Only need the top of the file
    except OSError:
        source = ""
    else:
        for sp in subproject_names:
            # Match patterns like: os.path.join(..., "api-gateway")
            # or os.path.join(..., "api-gateway"))
            if f'"{sp}"' in source or f"'{sp}'" in source:
                sys.path.insert(0, os.path.join(repo_root, sp))
                break

    # 4. Cross-package aliases (Phase 7) — cheap and idempotent, so always
    #    on rather than gated per-subproject.
    _ensure_cross_package_alias(repo_root, "vector-store", "vector_store")
    _ensure_cross_package_alias(repo_root, "rag-engine", "rag_engine")
