"""PatientVectorHub — Vector Store service configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_GRPC_PORT: int = 50051
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334
    EMBEDDING_MODEL_VERSION: str = "clinical-bert-v2.1"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = VectorSettings()
