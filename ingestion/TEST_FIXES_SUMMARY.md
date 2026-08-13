# Ingestion Service Test Fixes Summary

## Date: 2026-08-13

## Issues Fixed

### 1. Configuration Test Failures (3 tests)
**Problem**: Tests were checking for attributes that don't exist in the ingestion service config:
- `cors_origins_list` - This belongs to the API gateway service
- `LLM_MAX_TOKENS` - This belongs to the RAG engine service  
- `API_PORT` - This belongs to the API gateway service

**Solution**: Replaced these tests with ingestion-specific configuration tests:
- `test_embedding_provider_is_valid()` - Validates EMBEDDING_PROVIDER setting
- `test_embedding_dimensions_positive()` - Validates EMBEDDING_DIMENSIONS is positive
- `test_kafka_brokers_configured()` - Validates Kafka brokers are configured

**Files Modified**: `ingestion/tests/unit/test_config.py`

### 2. LLM Router Module Not Found (15 tests)
**Problem**: `test_llm_router.py` was testing `src.llm_router` module which doesn't exist in the ingestion service. The `llm_router` module belongs to the `rag-engine` service.

**Solution**: Deleted `ingestion/tests/unit/test_llm_router.py` since it was misplaced. The correct test file already exists at `rag-engine/tests/unit/test_llm_router.py`.

**Files Deleted**: `ingestion/tests/unit/test_llm_router.py`

### 3. SSL Certificate File Path Issue (1 test)
**Problem**: `test_publish_to_dlq_sends_expected_payload` was failing because it tried to load SSL certificates from `certs\ca.pem` during unit tests. Unit tests should not require external resources like certificates.

**Solution**: Modified the test to mock `kafka_client_kwargs()` to return a minimal plaintext configuration, avoiding SSL certificate loading during unit tests.

**Files Modified**: `ingestion/tests/unit/test_ingestion_dlq.py`

### 4. Integration Test Issues (Not Fixed)
**Problem**: Integration test `test_forced_failure_lands_on_dlq_and_marks_document_failed` fails because it requires:
- Active database connection to Aiven cloud PostgreSQL
- Network connectivity to external services

**Status**: This is expected behavior for integration tests. They should be:
- Run in CI/CD with proper environment setup
- Skipped locally unless specifically testing against real services
- Marked with `@pytest.mark.integration` and run separately from unit tests

**Recommendation**: Run only unit tests locally with:
```bash
pytest .\tests\unit\ -v
```

## Test Results

### Before Fixes
- **Failed**: 18 tests
- **Passed**: 37 tests  
- **Skipped**: 1 test

### After Fixes
- **Failed**: 0 tests (unit tests only)
- **Passed**: 41 tests (unit tests only)
- **Skipped**: 0 tests (unit tests only)

## Key Takeaways

1. **Service Boundaries**: Each service (api-gateway, ingestion, rag-engine) has its own configuration and tests should only reference that service's modules and settings.

2. **Unit vs Integration Tests**: Unit tests should not depend on external resources (databases, certificates, network services). Use mocking to isolate the code under test.

3. **Test Organization**: Tests for a module should live in the same service as the module itself. The `llm_router` tests belong in `rag-engine`, not `ingestion`.

4. **Integration Test Execution**: Integration tests should be run separately and require proper environment setup with real services available.
