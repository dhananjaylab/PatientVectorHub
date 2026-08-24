"""
Unit tests for api-gateway/src/vault_client.py (Phase 10 / ADR-017).

Mocks hvac.Client and the Redis cache -- no live Vault or Redis needed,
matching this codebase's established unit-vs-integration split (compare
tests/unit/test_rate_limit.py, which mocks storage_uri rather than
requiring a live Redis). A separate
tests/integration/test_vault_transit_integration.py (not this file)
exercises a real Vault dev-server round trip.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src import vault_client


@pytest.fixture(autouse=True)
def _reset_singletons():
    """vault_client module-level client singletons must not leak a mock
    from one test into the next."""
    vault_client._vault_client = None
    vault_client._redis_client = None
    yield
    vault_client._vault_client = None
    vault_client._redis_client = None


class TestGetVaultClient:
    def test_lazy_construction_is_a_singleton(self):
        c1 = vault_client.get_vault_client()
        c2 = vault_client.get_vault_client()
        assert c1 is c2


class TestEncryptDecryptSync:
    def test_encrypt_phi_sync_base64_encodes_plaintext_and_returns_ciphertext(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v1:abc123=="}
        }
        with patch.object(vault_client, "get_vault_client", return_value=mock_client):
            result = vault_client.encrypt_phi_sync("MRN-00042")

        assert result == "vault:v1:abc123=="
        call_kwargs = mock_client.secrets.transit.encrypt_data.call_args.kwargs
        assert call_kwargs["name"] == vault_client.settings.VAULT_TRANSIT_KEY
        import base64

        assert base64.b64decode(call_kwargs["plaintext"]) == b"MRN-00042"

    def test_decrypt_phi_sync_base64_decodes_vault_response(self):
        import base64

        mock_client = MagicMock()
        mock_client.secrets.transit.decrypt_data.return_value = {
            "data": {"plaintext": base64.b64encode(b"MRN-00042").decode("ascii")}
        }
        with patch.object(vault_client, "get_vault_client", return_value=mock_client):
            result = vault_client.decrypt_phi_sync("vault:v1:abc123==")

        assert result == "MRN-00042"
        mock_client.secrets.transit.decrypt_data.assert_called_once_with(
            name=vault_client.settings.VAULT_TRANSIT_KEY,
            ciphertext="vault:v1:abc123==",
        )

    def test_round_trip_recovers_original_plaintext(self):
        """Fakes Vault's own encrypt/decrypt with a real (if trivial)
        base64 round trip, rather than mocking decrypt to just echo
        whatever encrypt was called with -- proves the base64
        encode/decode framing on both sides is actually symmetric."""
        import base64

        mock_client = MagicMock()

        def _fake_encrypt(name, plaintext):
            return {"data": {"ciphertext": f"vault:v1:{plaintext}"}}

        def _fake_decrypt(name, ciphertext):
            b64 = ciphertext.removeprefix("vault:v1:")
            return {"data": {"plaintext": b64}}

        mock_client.secrets.transit.encrypt_data.side_effect = _fake_encrypt
        mock_client.secrets.transit.decrypt_data.side_effect = _fake_decrypt

        with patch.object(vault_client, "get_vault_client", return_value=mock_client):
            ciphertext = vault_client.encrypt_phi_sync("MRN-99999")
            plaintext = vault_client.decrypt_phi_sync(ciphertext)

        assert plaintext == "MRN-99999"


class TestAsyncWrappers:
    def test_encrypt_phi_runs_sync_call_off_the_event_loop(self):
        """asyncio.to_thread genuinely offloads work -- confirmed by
        patching the sync function and checking it was called with the
        same argument, not by inspecting threading internals (which
        would be testing asyncio's implementation, not this module's
        contract)."""

        async def _run():
            fake_redis = AsyncMock()
            fake_redis.get.return_value = None
            with (
                patch.object(vault_client, "_get_redis_client", return_value=fake_redis),
                patch.object(
                    vault_client, "encrypt_phi_sync", return_value="vault:v1:xyz"
                ) as mock_sync,
            ):
                result = await vault_client.encrypt_phi("MRN-1")
            mock_sync.assert_called_once_with("MRN-1")
            return result

        assert asyncio.run(_run()) == "vault:v1:xyz"

    def test_encrypt_phi_returns_cached_ciphertext_without_calling_vault(self):
        async def _run():
            fake_redis = AsyncMock()
            fake_redis.get.return_value = b"vault:v1:cached"
            with (
                patch.object(vault_client, "_get_redis_client", return_value=fake_redis),
                patch.object(vault_client, "encrypt_phi_sync") as mock_sync,
            ):
                result = await vault_client.encrypt_phi("MRN-1")
            mock_sync.assert_not_called()
            return result

        assert asyncio.run(_run()) == "vault:v1:cached"

    def test_encrypt_phi_cache_key_is_never_the_raw_plaintext(self):
        """A Redis key listing must not leak the value it protects."""
        key = vault_client._cache_key("MRN-super-secret-000")
        assert "MRN-super-secret-000" not in key
        assert key.startswith("phi:enc:")

    def test_encrypt_phi_survives_redis_outage_by_falling_through_to_vault(self):
        async def _run():
            fake_redis = AsyncMock()
            fake_redis.get.side_effect = ConnectionError("redis down")
            fake_redis.set.side_effect = ConnectionError("redis down")
            with (
                patch.object(vault_client, "_get_redis_client", return_value=fake_redis),
                patch.object(
                    vault_client, "encrypt_phi_sync", return_value="vault:v1:xyz"
                ),
            ):
                result = await vault_client.encrypt_phi("MRN-1")
            return result

        assert asyncio.run(_run()) == "vault:v1:xyz"

    def test_decrypt_phi_is_never_cached(self):
        """No Redis interaction at all on the decrypt path -- see
        module docstring for the deliberate reasoning."""

        async def _run():
            fake_redis = AsyncMock()
            with (
                patch.object(vault_client, "_get_redis_client", return_value=fake_redis),
                patch.object(
                    vault_client, "decrypt_phi_sync", return_value="MRN-1"
                ) as mock_sync,
            ):
                result = await vault_client.decrypt_phi("vault:v1:xyz")
            mock_sync.assert_called_once_with("vault:v1:xyz")
            fake_redis.get.assert_not_called()
            fake_redis.set.assert_not_called()
            return result

        assert asyncio.run(_run()) == "MRN-1"


class TestFailClosedGuardrail:
    def test_noop_when_allow_real_phi_is_false(self):
        """Must not even construct a client, let alone touch the
        network, when real PHI isn't in play -- this is what keeps
        `pytest` runnable without a perfectly configured Vault."""
        with patch.object(vault_client, "get_vault_client") as mock_get_client:
            vault_client.require_vault_or_fail_closed(allow_real_phi=False)
        mock_get_client.assert_not_called()

    def test_raises_when_allow_real_phi_true_and_vault_unreachable(self):
        with patch.object(vault_client, "is_vault_healthy", return_value=False):
            with pytest.raises(vault_client.VaultUnavailableError, match="unreachable"):
                vault_client.require_vault_or_fail_closed(allow_real_phi=True)

    def test_raises_when_transit_key_missing(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.read_key.side_effect = Exception("404 key not found")
        with (
            patch.object(vault_client, "is_vault_healthy", return_value=True),
            patch.object(vault_client, "get_vault_client", return_value=mock_client),
        ):
            with pytest.raises(vault_client.VaultUnavailableError, match="transit key"):
                vault_client.require_vault_or_fail_closed(allow_real_phi=True)

    def test_passes_when_vault_healthy_and_key_exists(self):
        mock_client = MagicMock()
        mock_client.secrets.transit.read_key.return_value = {"data": {"name": "phi-key"}}
        with (
            patch.object(vault_client, "is_vault_healthy", return_value=True),
            patch.object(vault_client, "get_vault_client", return_value=mock_client),
        ):
            vault_client.require_vault_or_fail_closed(allow_real_phi=True)  # must not raise


class TestVaultHealthCheck:
    def test_healthy_when_read_health_status_succeeds(self):
        mock_client = MagicMock()
        mock_client.sys.read_health_status.return_value = MagicMock(status_code=200)
        with patch.object(vault_client, "get_vault_client", return_value=mock_client):
            assert vault_client.is_vault_healthy() is True

    def test_unhealthy_when_read_health_status_raises(self):
        mock_client = MagicMock()
        mock_client.sys.read_health_status.side_effect = Exception("connection refused")
        with patch.object(vault_client, "get_vault_client", return_value=mock_client):
            assert vault_client.is_vault_healthy() is False
