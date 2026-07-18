"""
PatientVectorHub — API Gateway configuration.
Uses Pydantic BaseSettings for type-safe environment variable loading.
All values can be overridden via environment variables or .env file.
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

    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""


    # ── Embedding ─────────────────────────────────────────────────────────────
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"

    # ── Vault ─────────────────────────────────────────────────────────────────
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"
    # Production: VAULT_TOKEN unused — K8s ServiceAccount auth via Vault agent

    # ── Keycloak ──────────────────────────────────────────────────────────────
    KEYCLOAK_BASE_URL: str = "http://localhost:8443"
    KEYCLOAK_REALM: str = "patientvectorhub"
    KEYCLOAK_JWKS_URL: str = (
        "http://localhost:8443/realms/patientvectorhub"
        "/protocol/openid-connect/certs"
    )
    KEYCLOAK_ISSUER: str = (
        "http://localhost:8443/realms/patientvectorhub"
    )
    KEYCLOAK_CLIENT_ID: str = "pvh-spa"

    # ── LLM Providers ─────────────────────────────────────────────────────────
    LLM_DEFAULT_PROVIDER: str = "anthropic"
    LLM_MAX_TOKENS: int = 1000
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # ── Cloudflare R2 / Storage ───────────────────────────────────────────────
    R2_ENDPOINT_URL: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_DOCUMENT_BUCKET: str = "pvh-documents-dev"
    R2_BACKUP_BUCKET: str = "pvh-backups-dev"

    # ── Observability ─────────────────────────────────────────────────────────
    JAEGER_ENDPOINT: str = "http://localhost:4317"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    # ── App ───────────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://localhost:3000,https://app.pvh.internal"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS into a list."""
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT in ("development", "dev")


# Module-level singleton — import this everywhere
settings = Settings()
