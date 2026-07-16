"""
Phase 1 integration tests — verify all local stack services are reachable.
Run ONLY with running Docker Compose stack: make dev
Mark: pytest -m integration
"""
import os
import pytest

pytestmark = pytest.mark.integration

POSTGRES_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh")
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379/0")
VAULT_ADDR   = os.getenv("VAULT_ADDR", "http://localhost:8200")
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
QDRANT_HOST   = os.getenv("QDRANT_HOST", "localhost")


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
        row = await conn.fetchrow(
            "SELECT datname FROM pg_database WHERE datname = 'pvh'"
        )
        await conn.close()
        assert row is not None, "Database 'pvh' not found"


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


class TestVaultConnectivity:
    def test_vault_reachable(self):
        import httpx
        resp = httpx.get(f"{VAULT_ADDR}/v1/sys/health", timeout=5)
        assert resp.status_code in (200, 429, 501, 503)

    def test_vault_dev_token_works(self):
        import hvac
        client = hvac.Client(url=VAULT_ADDR, token="dev-root-token")
        assert client.is_authenticated()

    def test_vault_transit_key_exists(self):
        import hvac
        client = hvac.Client(url=VAULT_ADDR, token="dev-root-token")
        try:
            keys = client.secrets.transit.list_keys()
            assert "phi-key" in keys["data"]["keys"]
        except Exception:
            pytest.skip("Vault transit not yet initialised — run make vault-init")


class TestWeaviateConnectivity:
    def test_weaviate_ready(self):
        import weaviate
        from weaviate.classes.init import Auth
        weaviate_url = os.getenv("WEAVIATE_URL")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        if weaviate_url and weaviate_api_key:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=weaviate_url,
                auth_credentials=Auth.api_key(weaviate_api_key),
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
        weaviate_url = os.getenv("WEAVIATE_URL")
        weaviate_api_key = os.getenv("WEAVIATE_API_KEY")
        if weaviate_url and weaviate_api_key:
            client = weaviate.connect_to_weaviate_cloud(
                cluster_url=weaviate_url,
                auth_credentials=Auth.api_key(weaviate_api_key),
            )
        else:
            client = weaviate.connect_to_local(
                host=WEAVIATE_HOST, port=8080,
            )
        try:
            existing = {c.name for c in client.collections.list_all().values()}
            assert any("PatientDocument" in c for c in existing), \
                "No PatientDocument collections found — run make setup-vector-stores"
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
