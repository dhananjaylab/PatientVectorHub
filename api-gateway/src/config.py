"""
PatientVectorHub — API Gateway configuration.
Uses Pydantic BaseSettings for type-safe environment variable loading.
All values can be overridden via environment variables or .env file.

Phase 4 fix: added KAFKA_SECURITY_PROTOCOL / KAFKA_USERNAME /
KAFKA_PASSWORD / KAFKA_SASL_MECHANISM / KAFKA_SSL_CAFILE — main.py's
Kafka producer setup already read these via getattr(settings, ..., default)
so it never crashed without them, but with extra="ignore" below, any
matching env vars were being silently dropped rather than attached to
`settings` — meaning SASL/SSL auth could never actually engage no matter
what was set in .env. Mirrors the same fields already added to
ingestion/src/config.py.
"""
from pathlib import Path

from pydantic import model_validator
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

    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    QDRANT_HOST: str = "localhost"
    # 6333 = REST port (AsyncQdrantClient's port= kwarg); 6334 is gRPC, a
    # separate kwarg this codebase doesn't use. Was 6334 (wrong) before
    # Phase 6/ADR-013 — see vector-store/src/config.py for the full note.
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""


    # ── Embedding ─────────────────────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"

    # ── Vault ─────────────────────────────────────────────────────────────────
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"
    # Production: VAULT_TOKEN unused — K8s ServiceAccount auth via Vault agent

    # -- Auth ---------------------------------------------------------------------
    AUTH_ENABLED: bool = False

    # -- Keycloak -----------------------------------------------------------------
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

    @model_validator(mode="after")
    def _resolve_ssl_paths(self):
        """Resolve relative certificate paths against the repo root.

        The project stores certs under the repo-level /certs folder, while
        .env entries like `certs\ca.pem` are typically written relative to the
        repository root rather than the API gateway subdirectory. Without this,
        startup fails with FileNotFoundError even though the cert exists.
        """
        repo_root = Path(__file__).resolve().parents[2]
        for field in ("KAFKA_SSL_CAFILE", "KAFKA_SSL_CERTFILE", "KAFKA_SSL_KEYFILE"):
            value = getattr(self, field, "")
            if not value:
                continue
            candidate = Path(value)
            if candidate.is_absolute():
                continue
            resolved = (repo_root / candidate).resolve()
            if resolved.exists():
                setattr(self, field, str(resolved))
        return self


# Module-level singleton — import this everywhere
settings = Settings()
