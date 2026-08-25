import sys
import os
from unittest.mock import Mock, patch

import pytest

# Import seed_data from infra/scripts directory
infra_scripts_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "scripts"))
sys.path.insert(0, infra_scripts_path)
import seed_data

def test_seed_data_reset_clears_known_tenant_rows() -> None:
    conn = Mock()

    seed_data._reset_seed_data(conn)

    assert conn.execute.call_count >= 4


class TestResolveMrn:
    """Phase 10 / ADR-017."""

    def test_fake_mrn_is_deterministic_and_vault_ciphertext_shaped(self):
        a = seed_data.fake_mrn("seed-1")
        b = seed_data.fake_mrn("seed-1")
        c = seed_data.fake_mrn("seed-2")
        assert a == b
        assert a != c
        assert a.startswith("vault:v1:SEED_")

    def test_resolve_mrn_calls_real_mrn_when_vault_ready(self):
        with patch.object(seed_data, "real_mrn", return_value="vault:v1:REALCIPHER") as mock_real:
            result = seed_data.resolve_mrn("seed-1", vault_ready=True)
        mock_real.assert_called_once_with("seed-1")
        assert result == "vault:v1:REALCIPHER"

    def test_resolve_mrn_falls_back_to_fake_when_vault_not_ready_and_allow_real_phi_false(self):
        with patch.object(seed_data, "ALLOW_REAL_PHI", False):
            result = seed_data.resolve_mrn("seed-1", vault_ready=False)
        assert result == seed_data.fake_mrn("seed-1")

    def test_resolve_mrn_fails_closed_when_vault_not_ready_and_allow_real_phi_true(self):
        """Mirrors vault_client.py's require_vault_or_fail_closed() —
        an environment that's supposed to handle real PHI must never
        silently fall back to an unencrypted-shaped placeholder."""
        with patch.object(seed_data, "ALLOW_REAL_PHI", True):
            with pytest.raises(RuntimeError, match="ALLOW_REAL_PHI"):
                seed_data.resolve_mrn("seed-1", vault_ready=False)

    def test_real_mrn_base64_encodes_synthetic_plaintext_and_returns_vault_ciphertext(self):
        mock_client = Mock()
        mock_client.secrets.transit.encrypt_data.return_value = {
            "data": {"ciphertext": "vault:v1:abc123=="}
        }
        with patch.object(seed_data, "_get_vault_client", return_value=mock_client):
            result = seed_data.real_mrn("tenant-a-0")

        assert result == "vault:v1:abc123=="
        call_kwargs = mock_client.secrets.transit.encrypt_data.call_args.kwargs
        assert call_kwargs["name"] == seed_data.VAULT_TRANSIT_KEY
        import base64

        decoded = base64.b64decode(call_kwargs["plaintext"]).decode()
        assert decoded == seed_data._mrn_plaintext_for_seed("tenant-a-0")
        # Never the raw seed itself, and never anything claiming to be a
        # real medical record number -- this file's own module docstring
        # promise ("NO real PHI") holds even for the plaintext that gets
        # encrypted, not just the final stored value.
        assert "tenant-a-0" not in decoded

    def test_vault_ready_false_when_hvac_not_installed(self):
        with patch.object(seed_data, "hvac", None):
            assert seed_data._vault_ready() is False

    def test_vault_ready_false_when_health_check_raises(self):
        mock_client = Mock()
        mock_client.sys.read_health_status.side_effect = Exception("connection refused")
        with patch.object(seed_data, "hvac", Mock()), patch.object(
            seed_data, "_get_vault_client", return_value=mock_client
        ):
            assert seed_data._vault_ready() is False

    def test_vault_ready_false_when_transit_key_missing(self):
        mock_client = Mock()
        mock_client.sys.read_health_status.return_value = None
        mock_client.secrets.transit.read_key.side_effect = Exception("404")
        with patch.object(seed_data, "hvac", Mock()), patch.object(
            seed_data, "_get_vault_client", return_value=mock_client
        ):
            assert seed_data._vault_ready() is False

    def test_vault_ready_true_when_health_and_key_both_succeed(self):
        mock_client = Mock()
        mock_client.sys.read_health_status.return_value = None
        mock_client.secrets.transit.read_key.return_value = {"data": {"name": "phi-key"}}
        with patch.object(seed_data, "hvac", Mock()), patch.object(
            seed_data, "_get_vault_client", return_value=mock_client
        ):
            assert seed_data._vault_ready() is True
