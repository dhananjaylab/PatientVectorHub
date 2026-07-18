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
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = VectorSettings()
