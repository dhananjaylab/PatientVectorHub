"""
PatientVectorHub — Ingestion service configuration.
Full pydantic-settings implementation.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334

    # ── Embedding ─────────────────────────────────────────────────────────────
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"
    EMBEDDING_MODEL_VERSION: str = "clinical-bert-v2.1"

    # ── Vault ─────────────────────────────────────────────────────────────────
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"

    # ── AWS / Storage ─────────────────────────────────────────────────────────
    AWS_REGION: str = "us-east-1"
    S3_DOCUMENT_BUCKET: str = "pvh-documents-dev"
    S3_BACKUP_BUCKET: str = "pvh-backups-dev"

    # ── App ───────────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = Settings()
