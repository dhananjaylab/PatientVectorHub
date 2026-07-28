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

Phase 5 additions (ADR-012):
  - HF_TOKEN, HF_EMBEDDING_ENDPOINT_URL, HF_EMBEDDING_ENDPOINT_NAME,
    CLINICAL_BERT_MODEL_ID, CLINICAL_BERT_DIMENSIONS for the Hugging
    Face-hosted clinical embedding server (ingestion/src/embeddings/
    clinical_bert_embedder.py). EMBEDDING_MODEL_URL is retired — it
    pointed at the old local Docker embedding-server, which no longer
    exists.
  - model_post_init's PHI guardrail now also gates EMBEDDING_PROVIDER=
    clinical_bert, not just openai — a dedicated HF Inference Endpoint is
    still third-party infrastructure, not our own VPC.
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
    DATABASE_URL: str = "postgresql+asyncpg://pvh:pvh_local@localhost:5432/pvh"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://pvh:pvh_local@localhost:5432/pvh"

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
    # 6333 = REST port (AsyncQdrantClient's port= kwarg); 6334 is gRPC, a
    # separate kwarg this codebase doesn't use. Was 6334 (wrong) before
    # Phase 6/ADR-013 — see vector-store/src/config.py for the full note.
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""

    # ── Embedding (ADR-009: OpenAI default; ADR-012: HF-hosted clinical_bert) ─
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "clinical_bert"
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 1536
    EMBEDDING_BATCH_SIZE: int = 100
    OPENAI_API_KEY: str = ""

    # EMBEDDING_MODEL_URL is retired (ADR-012) — it pointed at the old local
    # Docker embedding-server ("http://localhost:8001"), which no longer
    # exists. Kept as an unused field, rather than deleted outright, only so
    # a stray reference to it in an existing .env doesn't hard-fail Settings
    # construction (extra="ignore" would already handle that — this comment
    # is the actual reason it's gone from active use). New deployments should
    # set HF_EMBEDDING_ENDPOINT_URL instead.
    EMBEDDING_MODEL_URL: str = ""

    # ── Hugging Face-hosted clinical embedding server (ADR-012) ───────────────
    # Populated after running scripts/deploy_hf_embedding_endpoint.py — this
    # is a manual, outside-of-CI provisioning step (see that script and
    # ADR-012's Consequences). Empty by default; embed_batch() in
    # clinical_bert_embedder.py will fail loudly on first real call if
    # EMBEDDING_PROVIDER=clinical_bert and this is still blank, rather than
    # silently talking to nothing.
    HF_TOKEN: str = ""
    HF_EMBEDDING_ENDPOINT_URL: str = ""
    HF_EMBEDDING_ENDPOINT_NAME: str = "pvh-clinical-embeddings"
    CLINICAL_BERT_MODEL_ID: str = "NeuML/pubmedbert-base-embeddings"
    CLINICAL_BERT_DIMENSIONS: int = 768

    # ── ADR-009 / ADR-012 compliance guardrail (Phase 4 plan §9) ──────────────
    # Neither the OpenAI path nor the HF-hosted clinical_bert path is
    # "self-hosted" in the sense the original Phase 5 plan meant (our own
    # VPC) — both send text to a third party's infrastructure. Real PHI
    # ingestion must not proceed on either path without both flags
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
        if (
            self.ALLOW_REAL_PHI
            and self.EMBEDDING_PROVIDER in ("openai", "clinical_bert")
            and not self.PHI_BAA_ACKNOWLEDGED
        ):
            raise RuntimeError(
                f"ALLOW_REAL_PHI=true with EMBEDDING_PROVIDER={self.EMBEDDING_PROVIDER!r} "
                "requires PHI_BAA_ACKNOWLEDGED=true to boot. See ADR-009 (OpenAI) "
                "and ADR-012 (Hugging Face-hosted clinical_bert): both send text "
                "to a third party's infrastructure, not our own VPC, and are "
                "accepted for synthetic-data development only until a signed "
                "BAA covers the relevant endpoint (a Hugging Face Enterprise "
                "BAA + private networking for clinical_bert, or an OpenAI BAA "
                "for openai)."
            )


settings = Settings()
