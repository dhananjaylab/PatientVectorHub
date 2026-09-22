"""
api-gateway/tests/security/test_jwt_adversarial.py — Phase 11 / ADR-018
Stage 11.4.

OWASP API2:2023 (Broken Authentication)-scoped. Zero existing coverage
of this before this phase: tests/unit/test_auth_middleware.py exercises
malformed/missing tokens and API-key edge cases, but never a
validly-shaped, maliciously-*signed* JWT — the actual attack class this
file covers.

Every forged token here is built from raw bytes (base64url header +
payload + signature), the same way tests/unit/test_auth_middleware.py's
docstring already notes real Keycloak verification was checked
manually, not via PyJWT's own jwt.encode() — verified directly that
PyJWT's encode() refuses outright to build an HS256 token from a PEM
asymmetric key ("should not be used as an HMAC secret"), which would
make the attack impossible to even construct if built that way. A real
attacker isn't using PyJWT's convenience wrapper to forge a token, so
neither does this test.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.requests import Request

from src.middleware.auth import KeycloakJWTMiddleware


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _raw_forge(header: dict, payload: dict, signature: bytes = b"") -> str:
    """Builds JWT wire bytes directly -- no PyJWT involved in
    construction, matching how a real attacker (who doesn't have a
    "please sign this for me" API) would actually do it."""
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = b".".join(segments)
    segments.append(_b64url(signature) if signature else b"")
    return b".".join(segments).decode()


@pytest.fixture(scope="module")
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_key, public_key, public_pem


@pytest.fixture
def app_with_mocked_jwks(keypair, monkeypatch):
    """Same minimal-app pattern as test_auth_middleware.py's
    TestMiddlewareRequestHandling, extended to mock PyJWKClient so a
    real signature-verification path actually runs (not just the
    malformed-token short-circuit those existing tests cover)."""
    from fastapi import FastAPI

    _, public_key, _ = keypair
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(request: Request):
        return {"role": getattr(request.state, "role", None)}

    app.add_middleware(
        KeycloakJWTMiddleware,
        jwks_url="http://keycloak.invalid/realms/patientvectorhub/protocol/openid-connect/certs",
        public_paths=frozenset(),
    )

    class _FakeSigningKey:
        key = public_key

    async def _fake_get_signing_key(self, token):
        return _FakeSigningKey()

    monkeypatch.setattr(
        "jwt.PyJWKClient.get_signing_key_from_jwt",
        lambda self, token: _FakeSigningKey(),
    )
    return app


_ADMIN_PAYLOAD = {
    "sub": "attacker",
    "tenant_id": "00000000-0000-0000-0000-000000000001",
    "realm_access": {"roles": ["admin"]},
}


class TestAlgorithmConfusion:
    """The single most common real-world JWT vulnerability class: an
    RS256-issuing server whose verifier can be tricked into treating
    the (public, non-secret) RSA public key as an HMAC secret."""

    @pytest.mark.asyncio
    async def test_genuine_rs256_token_is_accepted(self, app_with_mocked_jwks, keypair):
        """Positive control -- if this fails, the attack tests below
        prove nothing (a middleware that rejects everything would
        "pass" them for the wrong reason)."""
        import jwt as pyjwt
        from httpx import ASGITransport, AsyncClient

        private_key, _, _ = keypair
        good_token = pyjwt.encode(_ADMIN_PAYLOAD, private_key, algorithm="RS256")

        async with AsyncClient(
            transport=ASGITransport(app=app_with_mocked_jwks), base_url="http://t"
        ) as c:
            resp = await c.get("/whoami", headers={"Authorization": f"Bearer {good_token}"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    @pytest.mark.asyncio
    async def test_hs256_signed_with_public_key_is_rejected(
        self, app_with_mocked_jwks, keypair
    ):
        """The attack: PyJWKClient's cache is realm-scoped, so an
        attacker who has ever seen this realm's public signing key
        (served openly at /protocol/openid-connect/certs -- that's the
        point of a JWKS endpoint) can try using it as an HMAC-SHA256
        secret instead. If the verifier doesn't pin its accepted
        algorithm list, jwt.decode() will happily verify an HS256
        signature against that same key material, and the attacker's
        self-signed token (with whatever claims they want -- admin
        role, any tenant_id) sails through.
        """
        _, _, public_pem = keypair
        forged = _raw_forge(
            {"alg": "HS256", "typ": "JWT"},
            _ADMIN_PAYLOAD,
            signature=hmac.new(
                public_pem,
                _raw_forge({"alg": "HS256", "typ": "JWT"}, _ADMIN_PAYLOAD).rsplit(".", 1)[0].encode(),
                hashlib.sha256,
            ).digest(),
        )

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_mocked_jwks), base_url="http://t"
        ) as c:
            resp = await c.get("/whoami", headers={"Authorization": f"Bearer {forged}"})

        # auth.py pins algorithms=["RS256"] explicitly -- this must be
        # rejected at the algorithm-mismatch stage, never reach a point
        # where request.state.role could be set to "admin".
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    @pytest.mark.asyncio
    async def test_alg_none_is_rejected(self, app_with_mocked_jwks):
        """The other classic: a token that declares it has no
        signature at all. Some early JWT libraries treated this as
        "verification not applicable" and accepted the claims as-is."""
        forged = _raw_forge({"alg": "none", "typ": "JWT"}, _ADMIN_PAYLOAD)

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_mocked_jwks), base_url="http://t"
        ) as c:
            resp = await c.get("/whoami", headers={"Authorization": f"Bearer {forged}"})

        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"

    @pytest.mark.asyncio
    async def test_tampered_payload_after_genuine_signing_is_rejected(
        self, app_with_mocked_jwks, keypair
    ):
        """A different angle on the same integrity guarantee: start
        from a genuinely-signed token, then flip tenant_id in the
        payload segment without re-signing (simulating an attacker who
        can intercept/modify a token in transit but doesn't have the
        private key). The signature no longer matches the altered
        payload -- this is what actually makes tenant-ID spoofing
        infeasible for this architecture, more so than any
        application-level check could."""
        import jwt as pyjwt
        from httpx import ASGITransport, AsyncClient

        private_key, _, _ = keypair
        genuine = pyjwt.encode(_ADMIN_PAYLOAD, private_key, algorithm="RS256")
        header_b64, payload_b64, sig_b64 = genuine.split(".")

        tampered_payload = dict(_ADMIN_PAYLOAD)
        tampered_payload["tenant_id"] = "00000000-0000-0000-0000-000000000002"
        new_payload_b64 = _b64url(
            json.dumps(tampered_payload, separators=(",", ":")).encode()
        ).decode()
        tampered_token = f"{header_b64}.{new_payload_b64}.{sig_b64}"

        async with AsyncClient(
            transport=ASGITransport(app=app_with_mocked_jwks), base_url="http://t"
        ) as c:
            resp = await c.get(
                "/whoami", headers={"Authorization": f"Bearer {tampered_token}"}
            )
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "AUTHENTICATION_FAILED"
