"""
Embedding provider dispatch (ADR-012).

EMBEDDING_PROVIDER has existed in ingestion/src/config.py since Phase 4 but
nothing read it — batch_worker.py imported openai_embedder.embed_batch
directly. This module makes it real: callers should import embed_batch
from here, not from a specific provider module, so switching
EMBEDDING_PROVIDER actually changes what runs.

Default remains "openai" (ADR-009). Setting it to "clinical_bert" routes to
the Hugging Face-hosted embedder (ADR-012) — see that module and
ingestion/src/config.py's model_post_init guardrail before doing that with
real PHI.
"""

from ..config import settings


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed texts using whichever provider EMBEDDING_PROVIDER selects.

    Deliberately re-reads settings.EMBEDDING_PROVIDER on every call rather
    than binding a function reference at import time, so tests (and any
    future runtime config reload) that flip the setting see the change
    without re-importing this module.
    """
    provider = settings.EMBEDDING_PROVIDER
    if provider == "openai":
        from . import openai_embedder

        return await openai_embedder.embed_batch(texts)
    if provider == "clinical_bert":
        from . import clinical_bert_embedder

        return await clinical_bert_embedder.embed_batch(texts)
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER={provider!r} — expected 'openai' or "
        f"'clinical_bert' (see ADR-009, ADR-012)."
    )
