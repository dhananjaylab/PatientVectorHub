"""Unit tests for the PVH custom exception hierarchy."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))

import pytest
from src.errors import (
    PVHError, AuthenticationError, AuthorizationError,
    IngestionError, EmbeddingError, VectorStoreError,
    QueryError, LLMError, NotFoundError, TenantMismatchError,
)


class TestPVHErrorHierarchy:
    def test_pvh_error_is_exception(self):
        assert issubclass(PVHError, Exception)

    def test_pvh_error_default_status(self):
        assert PVHError.status_code == 500

    def test_authentication_error_status(self):
        assert AuthenticationError.status_code == 401

    def test_authorization_error_status(self):
        assert AuthorizationError.status_code == 403

    def test_not_found_error_status(self):
        assert NotFoundError.status_code == 404

    def test_ingestion_error_is_pvh_error(self):
        assert issubclass(IngestionError, PVHError)

    def test_embedding_error_is_ingestion_error(self):
        assert issubclass(EmbeddingError, IngestionError)

    def test_llm_error_status(self):
        assert LLMError.status_code == 503

    def test_vector_store_error_status(self):
        assert VectorStoreError.status_code == 503

    def test_tenant_mismatch_status(self):
        assert TenantMismatchError.status_code == 403


class TestPVHErrorInstantiation:
    def test_error_has_message(self):
        err = PVHError("something went wrong")
        assert err.message == "something went wrong"
        assert str(err) == "something went wrong"

    def test_error_has_detail(self):
        err = PVHError("failed", detail="extra context")
        assert err.detail == "extra context"

    def test_detail_defaults_to_none(self):
        err = PVHError("failed")
        assert err.detail is None

    def test_authentication_error_message(self):
        err = AuthenticationError("token expired")
        assert err.message == "token expired"
        assert err.error_code == "AUTHENTICATION_FAILED"

    def test_query_error_code(self):
        err = QueryError("bad query")
        assert err.error_code == "QUERY_ERROR"

    def test_ingestion_error_inherits_code(self):
        err = IngestionError("parse failed")
        assert err.error_code == "INGESTION_ERROR"

    def test_errors_are_catchable_as_pvh_error(self):
        with pytest.raises(PVHError):
            raise AuthorizationError("access denied")

    def test_errors_are_catchable_as_ingestion_error(self):
        with pytest.raises(IngestionError):
            raise EmbeddingError("embedding service down")


class TestErrorCodeUniqueness:
    def test_all_error_codes_unique(self):
        errors = [
            PVHError, AuthenticationError, AuthorizationError,
            IngestionError, EmbeddingError, VectorStoreError,
            QueryError, LLMError, NotFoundError, TenantMismatchError,
        ]
        codes = [e.error_code for e in errors]
        assert len(codes) == len(set(codes)), "Duplicate error codes found"
