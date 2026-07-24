"""
OpenAI embedding client for the ingestion pipeline (ADR-009).

Self-hosted clinical-bert is NOT used here. text-embedding-3-large is
confirmed current and not deprecated as of mid-2026 — see
docs/PHASE_4_IMPLEMENTATION_PLAN.md footnote [4]. Do not point this at
real PHI without re-confirming ADR-009's BAA caveat — see
ingestion/src/config.py's ALLOW_REAL_PHI / PHI_BAA_ACKNOWLEDGED guardrail.
"""
import logging

from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings

log = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    """Lazily construct the OpenAI client (not at module import time —
    see docs/PHASE_4_IMPLEMENTATION_PLAN.md for why this changed from an
    earlier draft: the current openai SDK raises OpenAIError immediately
    if api_key resolves to an empty/falsy value, which would crash on
    `import openai_embedder` alone in any environment without
    OPENAI_API_KEY set — CI, a fresh checkout before .env is filled in,
    etc. Failing at first real embedding call is the right place for
    that to surface, not at import time)."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "not-configured")
    return _client


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((RateLimitError, APIConnectionError, APITimeoutError)),
    reraise=True,
)
async def _embed_one_batch(texts: list[str]) -> list[list[float]]:
    response = await _get_client().embeddings.create(
        model=settings.EMBEDDING_MODEL_VERSION,      # "text-embedding-3-large"
        input=texts,
        dimensions=settings.EMBEDDING_DIMENSIONS,     # 1536, Matryoshka-shortened (ADR-009)
    )
    log.info(
        "embedded batch: n_texts=%d tokens=%d model=%s",
        len(texts), response.usage.total_tokens, settings.EMBEDDING_MODEL_VERSION,
    )
    return [d.embedding for d in response.data]


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of chunk texts, batching to stay within
    EMBEDDING_BATCH_SIZE (default 100 — comfortably under OpenAI's
    per-request input-array limits). Returns vectors in the same order as
    the input texts."""
    if not texts:
        return []
    batch_size = settings.EMBEDDING_BATCH_SIZE
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors.extend(await _embed_one_batch(batch))
    return vectors
