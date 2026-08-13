"""
Query embedder for the RAG query engine (Phase 7).

vector_store.interface.search() takes a required `query_vector` — per
ADR-013 §1, embedding the query text is deliberately the caller's job,
not vector_store's, to avoid vector_store depending on any embedding
provider. This module is that caller-side embedding step for the
`/v1/query` path specifically.

This duplicates ingestion/src/embeddings/{openai_embedder,
clinical_bert_embedder}.py's client construction and retry logic rather
than importing them. That's a deliberate choice, not an oversight: doing
the obvious-looking thing (`from ingestion.src.embeddings import
embed_batch`) would make rag-engine depend on ingestion — the same
dependency-inversion problem ADR-013 §1 already rejected for
vector_store, for the same reason (ingestion pulls in boto3, PyMuPDF,
python-hl7, and Celery, none of which the query path needs, and a
change to ingestion's batch-embedding internals shouldn't be able to
break query serving). See docs/adr/ADR-014-rag-query-engine.md §1.

Unlike the ingestion embedders, this only ever embeds one string at a
time (one query per request) — no batching loop needed.
"""

import logging

from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

log = logging.getLogger(__name__)


async def embed_query(text: str) -> list[float]:
    """Embed a single query string using whichever provider
    EMBEDDING_PROVIDER selects. Re-reads settings.EMBEDDING_PROVIDER on
    every call (not bound at import time) — same reasoning as
    ingestion/src/embeddings/__init__.py's embed_batch()."""
    provider = settings.EMBEDDING_PROVIDER
    if provider == "openai":
        return await _embed_query_openai(text)
    if provider == "clinical_bert":
        # Same tenacity-decorator type-erasure as llm_router.py's _call()
        # sites — annotating _embed_query_clinical_bert's own body wasn't
        # enough; the decorator loses the precise return type at this
        # call site from mypy's perspective.
        vector: list[float] = await _embed_query_clinical_bert(text)
        return vector
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER={provider!r} — expected 'openai' or "
        f"'clinical_bert' (see ADR-009, ADR-012)."
    )


# ── OpenAI (ADR-009 default) ────────────────────────────────────────────────

_openai_client = None


def _get_openai_client():
    """Lazily construct the OpenAI client — see
    ingestion/src/embeddings/openai_embedder.py's _get_client() for why
    this can't happen at import time (the installed openai SDK raises
    immediately on an empty api_key, which would crash on
    `import query_embedder` alone with OPENAI_API_KEY unset, e.g. in CI
    or a fresh checkout before .env is filled in)."""
    global _openai_client
    if _openai_client is None:
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "not-configured")
    return _openai_client


async def _embed_query_openai(text: str) -> list[float]:
    from openai import APIConnectionError, APITimeoutError, RateLimitError

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
        reraise=True,
    )
    async def _call() -> list[float]:
        response = await _get_openai_client().embeddings.create(
            model=settings.EMBEDDING_MODEL_VERSION,  # "text-embedding-3-large"
            input=[text],
            dimensions=settings.EMBEDDING_DIMENSIONS,  # 1536, Matryoshka-shortened (ADR-009)
        )
        embedding: list[float] = response.data[0].embedding
        return embedding

    result: list[float] = await _call()
    return result


# ── Hugging Face-hosted clinical_bert (ADR-012 alternate) ──────────────────

_hf_client = None


def _get_hf_client():
    global _hf_client
    if _hf_client is None:
        from huggingface_hub import AsyncInferenceClient

        _hf_client = AsyncInferenceClient(
            model=settings.HF_EMBEDDING_ENDPOINT_URL or None,
            token=settings.HF_TOKEN or None,
        )
    return _hf_client


def _is_retryable_hf_error(exc: BaseException) -> bool:
    """Mirrors ingestion/src/embeddings/clinical_bert_embedder.py's
    _is_retryable_hf_error() exactly — same reasoning: InferenceTimeoutError
    already covers cold-start/timeout; HfHubHTTPError only retries on
    429/5xx, not 4xx client errors that won't succeed on retry."""
    from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

    if isinstance(exc, InferenceTimeoutError):
        return True
    if isinstance(exc, HfHubHTTPError):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return status is not None and (status == 429 or status >= 500)
    return False


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception(_is_retryable_hf_error),
    reraise=True,
)
async def _embed_query_clinical_bert(text: str) -> list[float]:
    client = _get_hf_client()
    # feature_extraction() on a single string returns one row per token
    # against a non-pooling backend — but the deployed endpoint is a
    # TEI-backed dedicated deployment (ADR-012) that pools server-side,
    # so a single string in returns a single pooled vector out. Wrapping
    # in a one-item list keeps this call symmetric with
    # clinical_bert_embedder.py's batch call rather than relying on that
    # implicit single-string behavior being obviously correct on its own.
    raw = await client.feature_extraction([text], normalize=True)
    vectors: list[list[float]] = (
        raw.tolist() if hasattr(raw, "tolist") else [list(row) for row in raw]
    )
    log.info("embedded query (clinical_bert): model=%s", settings.CLINICAL_BERT_MODEL_ID)
    return vectors[0]
