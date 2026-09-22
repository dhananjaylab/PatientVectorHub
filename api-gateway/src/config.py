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

Phase 8 addition: RATE_LIMIT_ENABLED — gates
middleware/rate_limit.py's Limiter(enabled=...). Defaults True in every
real environment; test fixtures explicitly set this False (or monkeypatch
the module-level `limiter.enabled` directly — see
middleware/rate_limit.py's own docstring) so existing and new unit tests
that hit the same route repeatedly within one test run don't trip real
limits and produce flaky, unrelated 429s. No new Redis setting was added
for the limiter's storage backend — it reuses REDIS_URL, already shared
by Celery's broker/result backend (see middleware/rate_limit.py).

Phase 10 additions (Observability & Security):
- VAULT_TRANSIT_KEY — matches infra/scripts/vault_init.sh's already-
  seeded "phi-key" Transit key name; kept configurable rather than
  hardcoded in vault_client.py so a differently-named prod key doesn't
  require a code change.
- METRICS_ENABLED / TRACING_ENABLED — same "declared, not implied"
  posture as RATE_LIMIT_ENABLED: both default True, both exist so a
  single env var can turn either off (e.g. tracing off in a constrained
  local dev environment with no Jaeger running) without code changes.
- PROMETHEUS_MULTIPROC_DIR — empty by default (single-process dev
  server: uvicorn's own in-memory CollectorRegistry is correct there).
  MUST be set to a writable, EMPTY-ON-BOOT directory whenever
  API_WORKERS > 1 (gunicorn/uvicorn multi-worker prod deployment) — the
  default prometheus_client registry silently produces wrong (per-
  worker, not aggregated) numbers across processes without this. See
  observability.py's docstring for the concrete mechanism.
- PHI_CACHE_TTL_SECONDS — the risk register's own prescribed mitigation
  ("cache Vault-encrypted MRN values in Redis (1h TTL)"), not a value
  invented for this phase.
"""
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_asyncpg_url(raw_url: str) -> str:
    """Strip SSL query params while preserving the asyncpg driver.

    Aiven and similar Postgres providers often provide DSNs like
    ``...?ssl=require``. asyncpg accepts SSL via the connection call itself
    (or a custom SSL context), not by reusing a URL whose query string
    redefines the same runtime parameter after the socket is already open.
    The async SQLAlchemy engine must keep the ``+asyncpg`` driver prefix;
    dropping it turns the URL back into the sync psycopg2 path and causes
    ``InvalidRequestError: The asyncio extension requires an async driver``.
    """
    if not raw_url:
        return raw_url

    url = raw_url.strip()
    if "postgresql+asyncpg://" in url:
        normalized_scheme = "postgresql+asyncpg"
        url = url.replace("postgresql+asyncpg://", f"{normalized_scheme}://", 1)
    elif "postgresql+psycopg2://" in url:
        normalized_scheme = "postgresql+asyncpg"
        url = url.replace("postgresql+psycopg2://", f"{normalized_scheme}://", 1)
    elif "postgresql://" in url:
        normalized_scheme = "postgresql+asyncpg"
        url = url.replace("postgresql://", f"{normalized_scheme}://", 1)
    else:
        return raw_url.strip()

    parsed = urlsplit(url)
    if parsed.scheme not in {"postgresql", "postgresql+asyncpg"}:
        return raw_url.strip()

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key in ("ssl", "sslmode"):
        params.pop(key, None)

    clean_query = urlencode(params, doseq=True)
    return urlunsplit(
        ("postgresql+asyncpg", parsed.netloc, parsed.path, clean_query, parsed.fragment)
    )


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
    VAULT_TRANSIT_KEY: str = "phi-key"

    # ── PHI guardrail (Phase 10 / ADR-017) ──────────────────────────────────
    # Mirrors ingestion/src/config.py's own ALLOW_REAL_PHI, same name and
    # default, so one env var means the same thing across every service.
    # Gates vault_client.require_vault_or_fail_closed(), called from
    # lifespan() — when real PHI is in play, a Vault outage or a missing
    # phi-key transit key must abort startup, not silently boot into a
    # state that would let PHI persist unencrypted (fail-closed, matching
    # ADR-010's RLS posture, deliberately not middleware/rate_limit.py's
    # fail-open one — see vault_client.py's module docstring).
    ALLOW_REAL_PHI: bool = False

    # -- Auth ---------------------------------------------------------------------
    AUTH_ENABLED: bool = False

    # -- Keycloak -----------------------------------------------------------------
    KEYCLOAK_BASE_URL: str = "http://localhost:8443"
    KEYCLOAK_REALM: str = "patientvectorhub"
    # Deliberately derived from KEYCLOAK_BASE_URL + KEYCLOAK_REALM below
    # rather than trusted independently. The local dev paths here are
    # deterministic for every Keycloak realm, and letting these drift
    # separately is exactly how "dashboard login works, backend JWT
    # validation still points at the old port" regressions happen when
    # switching between the Docker-mapped host port (8443) and a
    # standalone Windows Keycloak start-dev on 8080.
    KEYCLOAK_JWKS_URL: str = ""
    KEYCLOAK_ISSUER: str = ""
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

    # ── Observability (Phase 10) ─────────────────────────────────────────────
    JAEGER_ENDPOINT: str = "http://localhost:4317"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    METRICS_ENABLED: bool = True
    TRACING_ENABLED: bool = True
    OTEL_SERVICE_NAME: str = "pvh-api-gateway"
    PROMETHEUS_MULTIPROC_DIR: str = ""
    PHI_CACHE_TTL_SECONDS: int = 3600

    # ── App ───────────────────────────────────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://localhost:3000,https://app.pvh.internal"
    )

    # ── Rate limiting (Phase 8 / ADR-015) ────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = True

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
    def _normalize_runtime_settings(self):
        """Normalize environment-driven runtime settings.

        1. Strip SSL query params from asyncpg DSNs before they are handed to
           asyncpg, because `ssl`/`sslmode` are runtime connection parameters and
           asyncpg rejects changing them after connection setup.
        2. Resolve relative cert paths against the repo root.
        3. Normalize Keycloak endpoints from the base URL + realm pair.
        """
        self.DATABASE_URL = normalize_asyncpg_url(self.DATABASE_URL)

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

        base_url = self.KEYCLOAK_BASE_URL.rstrip("/")
        realm = self.KEYCLOAK_REALM.strip("/")
        issuer = f"{base_url}/realms/{realm}"
        # Always normalize these to the deterministic Keycloak realm
        # endpoints so changing KEYCLOAK_BASE_URL or KEYCLOAK_REALM alone
        # cannot leave stale 8443/8080 values behind in copied .env files.
        self.KEYCLOAK_ISSUER = issuer
        self.KEYCLOAK_JWKS_URL = f"{issuer}/protocol/openid-connect/certs"
        return self


# Module-level singleton — import this everywhere
settings = Settings()
