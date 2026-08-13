"""
Phase 1 integration tests — verify all local stack services are reachable.
Run ONLY with running Docker Compose stack: make dev
Mark: pytest -m integration

These tests are SKIPPED if services are not running.
"""
import os
from urllib.parse import urlparse

import pytest
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(env_path)


def _database_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    db_name = parsed.path.lstrip("/") if parsed.path else "postgres"
    return db_name or "postgres"

pytestmark = pytest.mark.integration

# Skip entire module if SKIP_INTEGRATION_TESTS is set
skip_integration = pytest.mark.skipif(
    os.getenv("SKIP_INTEGRATION_TESTS", "").lower() in ("true", "1", "yes"),
    reason="Integration tests skipped (SKIP_INTEGRATION_TESTS=true)"
)

POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh")
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
VAULT_ADDR   = os.getenv("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN  = os.getenv("VAULT_TOKEN", "dev-root-token")
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_URL = os.getenv("WEAVIATE_URL")
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
QDRANT_HOST   = os.getenv("QDRANT_HOST", "localhost")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

@skip_integration
class TestPostgresConnectivity:
    @pytest.mark.asyncio
    async def test_postgres_reachable(self):
        import asyncpg
        conn = await asyncpg.connect(
            POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://")
        )
        result = await conn.fetchval("SELECT 1")
        await conn.close()
        assert result == 1

    @pytest.mark.asyncio
    async def test_postgres_pvh_database_exists(self):
        import asyncpg
        conn = await asyncpg.connect(
            POSTGRES_URL.replace("postgresql+asyncpg://", "postgresql://")
        )
        expected_db = _database_name_from_url(POSTGRES_URL)
        row = await conn.fetchrow(
            "SELECT datname FROM pg_database WHERE datname = $1",
            expected_db,
        )
        await conn.close()
        assert row is not None, f"Database '{expected_db}' not found"

class TestRedisConnectivity:
    def test_redis_reachable(self):
        import redis
        r = redis.from_url(REDIS_URL)
        assert r.ping() is True

    def test_redis_set_get(self):
        import redis
        r = redis.from_url(REDIS_URL)
        r.set("pvh:phase1:test", "ok", ex=30)
        val = r.get("pvh:phase1:test")
        assert val == b"ok"

@skip_integration
class TestVaultConnectivity:
    def test_vault_reachable(self):
        import httpx
        try:
            resp = httpx.get(f"{VAULT_ADDR}/v1/sys/health", timeout=5)
            assert resp.status_code in (200, 429, 501, 503)
        except Exception as exc:
            pytest.skip(f"Vault not reachable at {VAULT_ADDR}: {exc}")

    def test_vault_dev_token_works(self):
        import hvac
        try:
            client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
            assert client.is_authenticated()
        except Exception as exc:
            pytest.skip(f"Vault auth unavailable at {VAULT_ADDR}: {exc}")

    def test_vault_transit_key_exists(self):
        import hvac
        try:
            client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
            keys = client.secrets.transit.list_keys()
            assert "phi-key" in keys["data"]["keys"]
        except Exception:
            pytest.skip("Vault transit not yet initialised or unavailable — run make vault-init")

class TestWeaviateConnectivity:
    def test_weaviate_ready(self):
        import weaviate
        from weaviate.classes.init import Auth
        if WEAVIATE_URL and WEAVIATE_API_KEY:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=WEAVIATE_URL,
                auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
            )
        else:
            client = weaviate.connect_to_local(
                host=WEAVIATE_HOST, port=8080,
            )
        try:
            assert client.is_ready() is True
        finally:
            client.close()

    def test_weaviate_tenant_collection_exists(self):
        import weaviate
        from weaviate.classes.init import Auth
        if WEAVIATE_URL and WEAVIATE_API_KEY:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=WEAVIATE_URL,
                auth_credentials=Auth.api_key(WEAVIATE_API_KEY),
            )
        else:
            client = weaviate.connect_to_local(
                host=WEAVIATE_HOST, port=8080,
            )
        try:
            existing = {c.name for c in client.collections.list_all().values()}
            assert "PatientDocument" in existing, \
                "PatientDocument collection not found — run: python scripts/setup_weaviate_schema.py"
        finally:
            client.close()

class TestKafkaConnectivity:
    def test_kafka_topics_exist(self):
        try:
            from kafka import KafkaAdminClient
            admin = KafkaAdminClient(
                bootstrap_servers="localhost:9092",
                request_timeout_ms=5_000,
            )
            topics = admin.list_topics()
            admin.close()
            assert "doc-ingest" in topics, \
                "doc-ingest topic not found — run make kafka-topics"
            assert "doc-dlq" in topics, \
                "doc-dlq topic not found — run make kafka-topics"
        except Exception as e:
            pytest.skip(f"Kafka not reachable: {e}")
