"""
Hugging Face-hosted clinical embedding client for the ingestion pipeline
(ADR-012; supersedes ADR-009's "parked" framing of Phase 5 — the OpenAI
default from ADR-009 itself is unchanged).

Model and inference both run on a Hugging Face Inference Endpoint (Text
Embeddings Inference container) deployed via
scripts/deploy_hf_embedding_endpoint.py — nothing in this module runs
locally or in our own Docker image. See ADR-012 for why
NeuML/pubmedbert-base-embeddings was chosen over raw
emilyalsentzer/Bio_ClinicalBERT.

Do not point this at real PHI without re-confirming ADR-012's BAA caveat —
a dedicated HF Inference Endpoint is still Hugging Face's infrastructure,
not our own VPC. See ingestion/src/config.py's ALLOW_REAL_PHI /
PHI_BAA_ACKNOWLEDGED guardrail, which now also gates this provider.
"""

import logging

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import settings

log = logging.getLogger(__name__)

_client: AsyncInferenceClient | None = None


def _get_client() -> AsyncInferenceClient:
    """Lazily construct the Inference client (not at module import time —
    same reasoning as openai_embedder.py's _get_client(): constructing a
    network client eagerly at import time turns "HF_TOKEN not set yet"
    (e.g. a fresh checkout, or CI when EMBEDDING_PROVIDER=openai and this
    module is merely importable but unused) into an import-time crash
    instead of a first-real-call error).

    Passing the deployed endpoint's full URL as `model` sends requests
    directly to that dedicated endpoint, bypassing HF's serverless
    multi-provider routing — that routing exists for the shared Inference
    Providers marketplace, not for an endpoint you're already paying for.
    """
    global _client
    if _client is None:
        _client = AsyncInferenceClient(
            model=settings.HF_EMBEDDING_ENDPOINT_URL or None,
            token=settings.HF_TOKEN or None,
        )
    return _client


def _is_retryable_hf_error(exc: BaseException) -> bool:
    """InferenceTimeoutError already covers "model unavailable / request
    timed out" (the client itself retries HTTP 503 — TEI's cold-start
    status — internally before raising this). For HfHubHTTPError, only
    retry on 5xx/429; a 400/401/404 won't succeed on retry and should
    surface immediately."""
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
async def _embed_one_batch(texts: list[str]) -> list[list[float]]:
    client = _get_client()
    # feature_extraction() accepts a single string OR a list of strings in
    # one call. Against a non-pooling backend, a single string returns one
    # row *per token* (unpooled hidden states) — but our endpoint is a
    # TEI-backed dedicated deployment (ADR-012), and TEI pools server-side:
    # passing the whole batch returns exactly one row per input text, in
    # order. That's what makes a single call per batch correct here rather
    # than needing a token-aware reduction on our side.
    raw = await client.feature_extraction(
        texts,
        normalize=True,  # only honored on TEI-powered servers — see ADR-012
    )
    vectors = raw.tolist() if hasattr(raw, "tolist") else [list(row) for row in raw]
    log.info(
        "embedded batch (clinical_bert): n_texts=%d model=%s",
        len(texts),
        settings.CLINICAL_BERT_MODEL_ID,
    )
    return vectors


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of chunk texts, batching to stay within
    EMBEDDING_BATCH_SIZE. Returns vectors in the same order as the input
    texts. Vectors are CLINICAL_BERT_DIMENSIONS-dim (768 by default) —
    see ADR-012 §6 on why these are not interchangeable with the OpenAI
    provider's vectors in the same collection."""
    if not texts:
        return []
    batch_size = settings.EMBEDDING_BATCH_SIZE
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors.extend(await _embed_one_batch(batch))
    return vectors
