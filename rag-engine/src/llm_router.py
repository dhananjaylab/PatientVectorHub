"""
LLMRouter — dispatches a completion request to Anthropic (default),
OpenAI, or Gemini (Phase 7 / ADR-014).

Verified against the installed SDKs' actual behavior, not just docs
(this project's standard practice — see docs/PHASE_4_IMPLEMENTATION_PLAN.md
and docs/PHASE_6_IMPLEMENTATION_PLAN.md for the prior instances of this):

  - anthropic 0.120.2: AsyncAnthropic(api_key="") does NOT raise at
    construction (unlike openai's client). Still using the same
    `or "not-configured"` lazy-construction idiom as
    ingestion/src/embeddings/openai_embedder.py anyway, for two reasons:
    (1) consistency across all three providers in this file rather than
    one behaving differently for a reason a future reader has to
    rediscover, and (2) defensiveness against the anthropic SDK adding
    the same eager validation a future release, matching what openai's
    SDK already does.
  - openai 2.50.0: AsyncOpenAI(api_key="") DOES raise OpenAIError
    ("Missing credentials...") at construction — same behavior
    openai_embedder.py already works around; chat.completions.create()
    still accepts `max_tokens` (also accepts the newer
    `max_completion_tokens`, but the older parameter remains supported
    for chat.completions specifically, unlike the Responses API).
  - google-genai 2.14.0: genai.Client(api_key="") DOES raise ValueError
    at construction. Async calls go through `client.aio.models.
    generate_content(model=, contents=, config=GenerateContentConfig(
    max_output_tokens=...))`; response text via `response.text`.
    Exceptions live in google.genai.errors — ServerError (5xx) and
    ClientError (4xx, code attribute available) are the ones worth
    retrying on (429 specifically, not other 4xx).

Only one provider is actually exercised by the default config
(LLM_DEFAULT_PROVIDER=anthropic) — openai/gemini exist so llm_provider
can be overridden per request (QueryRequest.llm_provider — see
api-gateway/src/schemas/query.py), same shape as the original doc-14
LLMRouter design, just re-verified against currently-installed SDKs
instead of carried over unverified.
"""

import logging

from .config import settings

log = logging.getLogger(__name__)


class LLMRouter:
    """Stateless dispatcher — safe to instantiate once at module import
    time in routers/query.py (unlike the individual provider clients
    inside this module, which are each still lazily constructed on
    first real call)."""

    async def complete(
        self, prompt: str, provider: str | None = None, max_tokens: int | None = None
    ) -> str:
        provider = provider or settings.LLM_DEFAULT_PROVIDER
        max_tokens = max_tokens or settings.LLM_MAX_TOKENS
        if provider == "anthropic":
            return await _complete_anthropic(prompt, max_tokens)
        if provider == "openai":
            return await _complete_openai(prompt, max_tokens)
        if provider == "gemini":
            return await _complete_gemini(prompt, max_tokens)
        raise ValueError(
            f"Unknown llm_provider={provider!r} — expected 'anthropic', 'openai', or 'gemini'."
        )


# ── Anthropic (default) ─────────────────────────────────────────────────────

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic

        _anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY or "not-configured")
    return _anthropic_client


async def _complete_anthropic(prompt: str, max_tokens: int) -> str:
    from anthropic import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
        ),
        reraise=True,
    )
    async def _call() -> str:
        message = await _get_anthropic_client().messages.create(
            model=settings.LLM_ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # See this module's docstring — verified against the installed
        # SDK that content[0] is a TextBlock with a .text: str attribute
        # for a plain-text completion (no tool use configured). The
        # explicit annotation isn't decorative: anthropic's stub types
        # `.content` as a Union of block types, so `.text` resolves to
        # Any without it, which `warn_return_any` (pyproject.toml) flags.
        text: str = message.content[0].text
        return text

    result: str = await _call()
    return result


# ── OpenAI ───────────────────────────────────────────────────────────────────

_openai_llm_client = None


def _get_openai_llm_client():
    global _openai_llm_client
    if _openai_llm_client is None:
        from openai import AsyncOpenAI

        _openai_llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY or "not-configured")
    return _openai_llm_client


async def _complete_openai(prompt: str, max_tokens: int) -> str:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )
    from tenacity import (
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential,
    )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(
            (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
        ),
        reraise=True,
    )
    async def _call() -> str:
        response = await _get_openai_llm_client().chat.completions.create(
            model=settings.LLM_OPENAI_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        # openai's SDK types .content as `str | None` — None is possible
        # for e.g. a tool-call-only response, which shouldn't happen for
        # this plain-text completion but is worth a real error over a
        # silently wrong "None" string if it ever does.
        content: str | None = response.choices[0].message.content
        if content is None:
            raise ValueError("OpenAI chat.completions.create() returned no text content")
        return content

    result: str = await _call()
    return result


# ── Gemini ───────────────────────────────────────────────────────────────────

_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        _gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY or "not-configured")
    return _gemini_client


def _is_retryable_gemini_error(exc: BaseException) -> bool:
    from google.genai import errors

    if isinstance(exc, errors.ServerError):
        return True
    if isinstance(exc, errors.ClientError):
        return getattr(exc, "code", None) == 429
    return False


async def _complete_gemini(prompt: str, max_tokens: int) -> str:
    from google.genai import types
    from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception(_is_retryable_gemini_error),
        reraise=True,
    )
    async def _call() -> str:
        response = await _get_gemini_client().aio.models.generate_content(
            model=settings.LLM_GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=max_tokens),
        )
        text: str = response.text
        return text

    result: str = await _call()
    return result
