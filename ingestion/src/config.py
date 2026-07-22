"""
PatientVectorHub — Ingestion service configuration.
Full pydantic-settings implementation.
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


    # ── Embedding ─────────────────────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    # See vector-store/src/config.py for the full rationale — kept in sync
    # across ingestion/rag-engine/vector-store since all three need to agree
    # on the vector size written to/read from Qdrant and Weaviate.
    EMBEDDING_DIMENSIONS: int = 1536

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


settings = Settings()
