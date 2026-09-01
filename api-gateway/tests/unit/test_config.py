"""Focused regression tests for api-gateway/src/config.py."""

from src.config import Settings


class TestKeycloakSettings:
    def test_keycloak_urls_are_derived_from_base_url_and_realm(self):
        settings = Settings(
            _env_file=None,
            KEYCLOAK_BASE_URL="http://localhost:8080",
            KEYCLOAK_REALM="patientvectorhub",
        )

        assert settings.KEYCLOAK_ISSUER == "http://localhost:8080/realms/patientvectorhub"
        assert (
            settings.KEYCLOAK_JWKS_URL
            == "http://localhost:8080/realms/patientvectorhub/protocol/openid-connect/certs"
        )

    def test_stale_explicit_keycloak_urls_are_normalized_to_match_base_url(self):
        settings = Settings(
            _env_file=None,
            KEYCLOAK_BASE_URL="http://localhost:8080",
            KEYCLOAK_REALM="patientvectorhub",
            KEYCLOAK_ISSUER="http://localhost:8443/realms/patientvectorhub",
            KEYCLOAK_JWKS_URL=(
                "http://localhost:8443/realms/patientvectorhub/"
                "protocol/openid-connect/certs"
            ),
        )

        assert settings.KEYCLOAK_ISSUER == "http://localhost:8080/realms/patientvectorhub"
        assert (
            settings.KEYCLOAK_JWKS_URL
            == "http://localhost:8080/realms/patientvectorhub/protocol/openid-connect/certs"
        )
