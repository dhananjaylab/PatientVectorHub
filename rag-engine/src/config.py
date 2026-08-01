"""PatientVectorHub — RAG Engine configuration.

Phase 7 additions (ADR-014):
  - HF_TOKEN, HF_EMBEDDING_ENDPOINT_URL, CLINICAL_BERT_MODEL_ID,
    CLINICAL_BERT_DIMENSIONS — query_embedder.py's clinical_bert path
    needs the same fields ingestion/src/config.py already carries for
    its own (document) embedder. Values default to the same HF Inference
    Endpoint ingestion points at (scripts/deploy_hf_embedding_endpoint.py
    provisions one shared endpoint, not one per service) — override
    HF_EMBEDDING_ENDPOINT_URL only if that ever changes.
  - LLM_ANTHROPIC_MODEL / LLM_OPENAI_MODEL / LLM_GEMINI_MODEL — explicit,
    overridable model identifiers for llm_router.py, rather than
    hardcoding a model string per provider in code. Defaults verified
    against each provider's current API as of this phase (see
    docs/adr/ADR-014-rag-query-engine.md); this space moves fast enough
    that "current" is worth re-checking periodically, which is exactly
    why these are config, not constants.
  - ALLOW_REAL_PHI / PHI_BAA_ACKNOWLEDGED — query_embedder.py sends the
    analyst's free-text query to the same third-party providers
    (OpenAI / HF) ingestion's document embedder does. An analyst typing
    a patient name or MRN into the query box is the same PHI-egress
    concern ADR-009/ADR-012 already gate on the ingestion side; nothing
    about being on the query path makes that concern go away, so this
    mirrors ingestion/src/config.py's guardrail rather than leaving a
    second, unguarded egress path.
"""

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
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""

    # ── Query embedding (ADR-009 default / ADR-012 alternate) ─────────────────
    EMBEDDING_PROVIDER: str = "openai"  # "openai" | "clinical_bert"
    EMBEDDING_MODEL_URL: str = (
        "http://localhost:8001"  # retired, kept harmless — see ingestion/src/config.py
    )
    EMBEDDING_MODEL_VERSION: str = "text-embedding-3-large"
    # Kept in sync with ingestion/src/config.py and vector-store/src/config.py
    # — see the latter for the full rationale on the 1536 default.
    EMBEDDING_DIMENSIONS: int = 1536
    OPENAI_API_KEY: str = ""

    # ── Hugging Face-hosted clinical embedding server (ADR-012, mirrored) ─────
    HF_TOKEN: str = ""
    HF_EMBEDDING_ENDPOINT_URL: str = "https://api-inference.huggingface.co/pipeline/feature-extraction/NeuML/pubmedbert-base-embeddings"
    CLINICAL_BERT_MODEL_ID: str = "NeuML/pubmedbert-base-embeddings"
    CLINICAL_BERT_DIMENSIONS: int = 768

    # ── ADR-009 / ADR-012 compliance guardrail, mirrored from ingestion ───────
    ALLOW_REAL_PHI: bool = False
    PHI_BAA_ACKNOWLEDGED: bool = False

    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = "dev-root-token"

    # ── LLM synthesis (Phase 7 / ADR-014) ──────────────────────────────────────
    LLM_DEFAULT_PROVIDER: str = "anthropic"  # "anthropic" | "openai" | "gemini"
    LLM_MAX_TOKENS: int = 1000
    # OPENAI_API_KEY (defined above, in the embedding section) is reused
    # here — one OpenAI account key already covers both the embeddings
    # endpoint and chat.completions; no reason to carry two separate
    # settings for the same credential.
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Per-provider default model, each overridable independently of the
    # others. anthropic default chosen for balanced cost/quality on a
    # retrieval-grounded synthesis task (see ADR-014); openai/gemini are
    # alternate providers, not the default path, but still get an
    # explicit current-as-of-this-phase default rather than an empty
    # string that would only fail at first real call.
    LLM_ANTHROPIC_MODEL: str = "claude-sonnet-5"
    LLM_OPENAI_MODEL: str = "gpt-5.1"
    LLM_GEMINI_MODEL: str = "gemini-3.5-flash"

    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    def model_post_init(self, __context, /) -> None:  # pydantic v2 hook
        if (
            self.ALLOW_REAL_PHI
            and self.EMBEDDING_PROVIDER in ("openai", "clinical_bert")
            and not self.PHI_BAA_ACKNOWLEDGED
        ):
            raise RuntimeError(
                f"ALLOW_REAL_PHI=true with EMBEDDING_PROVIDER={self.EMBEDDING_PROVIDER!r} "
                "requires PHI_BAA_ACKNOWLEDGED=true to boot. Same guardrail as "
                "ingestion/src/config.py, mirrored here because query_embedder.py "
                "sends analyst query text to the same third-party providers — see "
                "ADR-009, ADR-012, and docs/adr/ADR-014-rag-query-engine.md §5."
            )


settings = RAGSettings()
