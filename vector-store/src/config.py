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
    QDRANT_PORT: int = 6334
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
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = VectorSettings()
