"""
PatientVectorHub — Vault Transit PHI encryption (Phase 10 / ADR-017).

Wraps HashiCorp Vault's Transit secrets engine to encrypt/decrypt the one
field in this schema that actually holds patient-identifying material at
rest: `patients.mrn` (db/models.py — currently plain String(255)).
infra/scripts/vault_init.sh has already enabled `transit` and created the
`phi-key` (aes256-gcm96) this module targets; infra/scripts/seed_data.py's
`fake_mrn()` already produces `vault:v1:...`-shaped placeholders, i.e. this
was scaffolded to be plugged in, not guessed at.

hvac.Client is a synchronous wrapper around `requests` — there is no
native async client (verified: inspected hvac.api.secrets_engines.Transit
directly; every method is a plain sync call). Running it straight from an
`async def` route would block the event loop for every encrypt/decrypt,
so the public async functions below run the sync hvac calls via
`asyncio.to_thread`, matching FastAPI's own recommended pattern for
wrapping blocking I/O rather than reaching for a third dependency.

Fail-closed, not fail-open — deliberately the opposite of
middleware/rate_limit.py's posture (ADR-015: an outage there should
degrade to "less protected", not "API down") and instead matching
ADR-010's RLS posture: a Vault outage while real PHI is in play must
never silently fall back to storing/returning plaintext. See
`require_vault_or_fail_closed()` below, called from main.py's lifespan.

Caching (risk register mitigation: "Cache Vault-encrypted MRN values in
Redis (1h TTL)"): this deliberately caches CIPHERTEXT keyed by a SHA-256
hash of the plaintext, not decrypted plaintext. Transit's AES-256-GCM
encryption is randomized per call (fresh nonce every time), so without
this, re-encrypting the same MRN twice — e.g. an idempotent re-seed or a
retried ingest — would mint a second, different-looking ciphertext for
identical input, which is merely wasteful, not incorrect. Caching the
ciphertext (not the plaintext) means Redis never holds decrypted PHI,
deliberately narrowing what a Redis compromise could expose, at the cost
of not speeding up decrypt-heavy read paths — there isn't one yet (no
route currently displays a decrypted MRN; see ADR-017 for the scope
note on why phi_reveal in the audit log is a separate UUID, not this
field).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging

import hvac
import redis.asyncio as redis_asyncio

from .config import settings

log = logging.getLogger(__name__)

_vault_client: hvac.Client | None = None
_redis_client: "redis_asyncio.Redis | None" = None


class VaultUnavailableError(RuntimeError):
    """Raised by the fail-closed boot check — never caught silently."""


def get_vault_client() -> hvac.Client:
    """Lazy singleton — constructing hvac.Client does not itself touch
    the network (verified directly), matching every other lazily-built
    client in this codebase (OpenAI, Anthropic, the rate limiter's
    Redis-backed Limiter). The first real request is what can fail."""
    global _vault_client
    if _vault_client is None:
        _vault_client = hvac.Client(url=settings.VAULT_ADDR, token=settings.VAULT_TOKEN)
    return _vault_client


def _get_redis_client() -> "redis_asyncio.Redis":
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_asyncio.Redis.from_url(settings.REDIS_URL)
    return _redis_client


def _cache_key(plaintext: str) -> str:
    # Never use the plaintext MRN itself as a Redis key -- a key listing
    # (`KEYS phi:enc:*` / slow-log entries) must not leak the value it's
    # protecting.
    digest = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return f"phi:enc:{digest}"


def is_vault_healthy() -> bool:
    """Sync -- used by both the fail-closed boot check (sync context,
    lifespan startup) and routers/health.py's existing
    `vault.sys.read_health_status()` call, which this module doesn't
    duplicate; app.state.vault is the same client this module returns."""
    try:
        get_vault_client().sys.read_health_status(method="GET")
        return True
    except Exception as e:  # noqa: BLE001 - health probe, any failure means "not healthy"
        log.warning("Vault health check failed: %s", e)
        return False


def require_vault_or_fail_closed(*, allow_real_phi: bool) -> None:
    """Boot-time guardrail, called from main.py's lifespan(). Mirrors
    ingestion/src/config.py's ALLOW_REAL_PHI / PHI_BAA_ACKNOWLEDGED
    pattern: when real PHI is in play, Vault must be reachable and
    `phi-key` must actually exist, or startup fails outright. When
    allow_real_phi is False (every non-BAA environment -- local dev,
    CI, most staging), this is a no-op: synthetic data has nothing that
    needs encrypting, and requiring a perfectly configured Vault just to
    run `pytest` would be its own footgun.
    """
    if not allow_real_phi:
        return
    client = get_vault_client()
    if not is_vault_healthy():
        raise VaultUnavailableError(
            "ALLOW_REAL_PHI is set but Vault is unreachable at "
            f"{settings.VAULT_ADDR} -- refusing to start rather than risk "
            "persisting real PHI unencrypted."
        )
    try:
        client.secrets.transit.read_key(name=settings.VAULT_TRANSIT_KEY)
    except Exception as e:  # noqa: BLE001
        raise VaultUnavailableError(
            f"ALLOW_REAL_PHI is set but transit key '{settings.VAULT_TRANSIT_KEY}' "
            f"does not exist or is unreadable -- run infra/scripts/vault_init.sh "
            f"first. Underlying error: {e}"
        ) from e


def encrypt_phi_sync(plaintext: str) -> str:
    """Core sync implementation -- also imported directly by
    infra/scripts/seed_data.py's real (non-fake) MRN path, which runs
    as a standalone script with its own sync SQLAlchemy engine and has
    no event loop to hand this off to. Returns Vault's own
    "vault:v<n>:<base64>" ciphertext format unmodified -- matches
    fake_mrn()'s placeholder shape in seed_data.py exactly, so the
    patients.mrn column never has two different value shapes depending
    on whether Vault was reachable when a row was written."""
    client = get_vault_client()
    b64_plaintext = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    response = client.secrets.transit.encrypt_data(
        name=settings.VAULT_TRANSIT_KEY,
        plaintext=b64_plaintext,
    )
    return response["data"]["ciphertext"]


def decrypt_phi_sync(ciphertext: str) -> str:
    """Core sync implementation. No Redis cache on this path -- see
    module docstring for why decrypt is deliberately NOT cached."""
    client = get_vault_client()
    response = client.secrets.transit.decrypt_data(
        name=settings.VAULT_TRANSIT_KEY,
        ciphertext=ciphertext,
    )
    b64_plaintext = response["data"]["plaintext"]
    return base64.b64decode(b64_plaintext).decode("utf-8")


async def encrypt_phi(plaintext: str) -> str:
    """Async wrapper for FastAPI routes. Redis-cached (ciphertext, not
    plaintext -- see module docstring) so repeatedly encrypting the same
    input within PHI_CACHE_TTL_SECONDS skips both the thread hop and the
    Vault round-trip."""
    cache_key = _cache_key(plaintext)
    r = _get_redis_client()
    try:
        cached = await r.get(cache_key)
        if cached is not None:
            return cached.decode("utf-8") if isinstance(cached, bytes) else cached
    except Exception as e:  # noqa: BLE001 - cache is an optimization, never a hard dependency
        log.warning("PHI encryption cache read failed, falling through to Vault: %s", e)

    ciphertext = await asyncio.to_thread(encrypt_phi_sync, plaintext)

    try:
        await r.set(cache_key, ciphertext, ex=settings.PHI_CACHE_TTL_SECONDS)
    except Exception as e:  # noqa: BLE001
        log.warning("PHI encryption cache write failed (non-fatal): %s", e)

    return ciphertext


async def decrypt_phi(ciphertext: str) -> str:
    """Async wrapper for FastAPI routes. Deliberately uncached -- see
    module docstring."""
    return await asyncio.to_thread(decrypt_phi_sync, ciphertext)
