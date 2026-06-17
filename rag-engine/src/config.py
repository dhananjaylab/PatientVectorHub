"""PatientVectorHub — RAG Engine configuration."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    REDIS_URL: str = "redis://localhost:6379/0"
    VECTOR_BACKEND: str = "weaviate"
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6334
    EMBEDDING_MODEL_URL: str = "http://localhost:8001"
    EMBEDDING_MODEL_VERSION: str = "clinical-bert-v2.1"
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
