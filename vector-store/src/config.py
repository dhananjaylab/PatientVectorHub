"""PatientVectorHub — Vector Store service configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    QDRANT_HOST: str = "localhost"
    # 6333 is Qdrant's REST/HTTP port — what AsyncQdrantClient's `port=`
    # kwarg expects (gRPC is a *separate* `grpc_port` kwarg, default 6334,
    # unused here since qdrant_store.py doesn't set prefer_grpc=True).
    # This was 6334 before Phase 6 (ADR-013) — a latent bug that never
    # surfaced because QdrantStore didn't exist yet to actually connect
    # with it. docker-compose.yml already exposes both 6333 and 6334.
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    # text-embedding-3-large is natively 3072-dim but supports OpenAI's
    # `dimensions` parameter to shorten it via Matryoshka representation
    # learning. 1536 is the default here: OpenAI's own benchmarks show a
    # 256-dim shortened text-embedding-3-large already beats full 1536-dim
    # ada-002, so 1536 keeps quality comfortably high while halving
    # Qdrant/Weaviate storage vs. the full 3072. This single setting is
    # the source of truth for scripts/setup_qdrant_schema.py's
    # VectorParams(size=...) — previously hardcoded to 768 (a leftover
    # from the pre-ADR-009 self-hosted clinical-bert plan). Change here,
    # not in the script, if a different dimension is needed; changing it
    # after any vectors have been written requires re-embedding, since
    # Qdrant collections have a fixed vector size.
    EMBEDDING_DIMENSIONS: int = 1536

    # ADR-012 introduced a second provider (clinical_bert, HF-hosted,
    # 768-dim) but that ADR explicitly flagged this file as not yet
    # dimension-aware for it. ADR-013 resolves that:
    # scripts/setup_qdrant_schema.py now picks EMBEDDING_DIMENSIONS or
    # CLINICAL_BERT_DIMENSIONS based on EMBEDDING_PROVIDER, instead of
    # always assuming the OpenAI path.
    CLINICAL_BERT_DIMENSIONS: int = 768

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = VectorSettings()
