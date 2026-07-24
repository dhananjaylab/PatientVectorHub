"""
PatientVectorHub — Ingestion service configuration.

Phase 4 additions over the Phase 1 stub:
  - Kafka SASL/SSL fields, promoted from scripts/create_kafka_topics.py's
    ad-hoc os.getenv() calls into typed Settings so batch_worker.py,
    stream_consumer.py, and dlq_producer.py don't each re-implement env
    parsing (see docs/PHASE_4_IMPLEMENTATION_PLAN.md §3.8/§3.9).
  - OPENAI_API_KEY, EMBEDDING_BATCH_SIZE for openai_embedder.py.
  - ALLOW_REAL_PHI / PHI_BAA_ACKNOWLEDGED — a small guardrail so ADR-009's
    "OpenAI embeddings are for synthetic data only" caveat is enforced by
    the app at boot, not just documented (see plan §9).
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Database ─────────────────────────────────────────────────────────────
    DATABASE_URL: str = (
        "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://pvh:pvh_local@localhost:5432/pvh"
    )

    # ── Cache & Messaging ─────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    KAFKA_BROKERS: str = "localhost:9092"
    KAFKA_SECURITY_PROTOCOL: str = "PLAINTEXT"
    KAFKA_USERNAME: str = ""
    KAFKA_PASSWORD: str = ""
    KAFKA_SASL_MECHANISM: str = "PLAIN"
    KAFKA_SSL_CAFILE: str = ""
    KAFKA_SSL_CERTFILE: str = ""
    KAFKA_SSL_KEYFILE: str = ""

    # ── Vector Stores ─────────────────────────────────────────────────────────
    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""

    # ── Embedding (ADR-009: OpenAI, not self-hosted clinical-bert) ────────────
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"   # parked — see ADR-009
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100
    OPENAI_API_KEY: str = ""

    # ── ADR-009 compliance guardrail (Phase 4 plan §9) ────────────────────────
    # OpenAI embeddings are accepted for synthetic-data development only.
    # Real PHI ingestion must not proceed on this path without both flags
    # explicitly set — see the model_post_init check below.
    ALLOW_REAL_PHI: bool = False
    PHI_BAA_ACKNOWLEDGED: bool = False

    # ── Vault ─────────────────────────────────────────────────────────────────
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"

    # ── Cloudflare R2 / Storage ───────────────────────────────────────────────
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_DOCUMENT_BUCKET: str = "pvh-documents-dev"
    R2_BACKUP_BUCKET: str = "pvh-backups-dev"

    # ── App ───────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    def model_post_init(self, __context) -> None:  # pydantic v2 hook
        if self.ALLOW_REAL_PHI and self.EMBEDDING_PROVIDER == "openai" and not self.PHI_BAA_ACKNOWLEDGED:
            raise RuntimeError(
                "ALLOW_REAL_PHI=true with EMBEDDING_PROVIDER=openai requires "
                "PHI_BAA_ACKNOWLEDGED=true to boot. See ADR-009: OpenAI "
                "embeddings are accepted for synthetic-data development only "
                "until a signed BAA covers the embeddings endpoint, or the "
                "self-hosted clinical-bert path is switched back on."
            )


settings = Settings()
