"""PatientVectorHub — RAG Engine configuration."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    REDIS_URL: str = "redis://localhost:6379/0"
    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_URL: str = ""
    WEAVIATE_API_KEY: str = ""
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    EMBEDDING_PROVIDER: str = "openai"
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"

    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"
    LLM_DEFAULT_PROVIDER: str = "anthropic"
    LLM_MAX_TOKENS: int = 1000
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"


settings = RAGSettings()
