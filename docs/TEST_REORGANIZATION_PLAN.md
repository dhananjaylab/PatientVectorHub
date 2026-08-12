# Test Reorganization Plan: Service-Based Structure

## Current Problem
- All tests mixed in a single `tests/` directory
- Each test file has to manually configure sys.path to import its service
- Different venv per service (api-gateway, ingestion, etc.) makes running all tests together difficult
- No clear separation of service boundaries

## Proposed Structure

### By Service

```
api-gateway/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_auth_middleware.py
│   │   ├── test_errors.py
│   │   ├── test_phase1_health.py
│   │   ├── test_query_router.py
│   │   ├── test_rbac.py
│   │   └── test_seed_data.py
│   └── integration/
│       └── test_rls_isolation*.py (5 files)
│       └── test_stack_connectivity.py
├── conftest.py (for IDE discovery)
└── pytest.ini

ingestion/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_embeddings_provider_routing.py
│   │   ├── test_ingestion_chunker.py
│   │   ├── test_ingestion_dlq.py
│   │   ├── test_ingestion_embedder.py
│   │   ├── test_ingestion_parsers.py
│   │   └── test_llm_router.py
│   └── integration/
│       ├── test_ingestion_dlq_end_to_end.py
│       └── test_ingestion_end_to_end.py
├── conftest.py (for IDE discovery)
└── pytest.ini

vector-store/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_qdrant_store.py
│   │   ├── test_vector_store_factory.py
│   │   ├── test_weaviate_schema.py
│   │   └── test_weaviate_search_delete.py
│   └── integration/
│       ├── test_vector_store_layer.py
│       └── test_dual_write_store.py
├── conftest.py (for IDE discovery)
└── pytest.ini

rag-engine/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_query_embedder.py
│   │   ├── test_rag_synthesizer.py
│   │   └── test_retriever.py
│   └── integration/
│       └── test_rag_query_pipeline.py
├── conftest.py (for IDE discovery)
└── pytest.ini

embedding-server/
├── tests/
│   ├── unit/
│   │   ├── test_clinical_bert_embedder.py
│   │   ├── test_hf_deploy_script.py
│   │   └── test_logging.py
│   └── conftest.py
├── conftest.py (for IDE discovery)
└── pytest.ini

dashboard/
├── tests/
│   └── (add as needed)
```

### Root Level (Keep for cross-service integration)

```
tests/
├── conftest.py (minimal — delegates to service conftest)
├── shared/
│   ├── test_db_models.py
│   └── conftest.py
└── pytest.ini (master config with markers)
```

## Test Categorization

### api-gateway/ service
- `test_auth_middleware.py` — middleware auth logic
- `test_rbac.py` — role-based access control
- `test_errors.py` — error handling
- `test_phase1_health.py` — health check endpoint
- `test_query_router.py` — query router endpoint
- `test_seed_data.py` — seed data utility
- `test_rls_isolation*.py` — RLS (Row Level Security) database policies
- `test_stack_connectivity.py` — infrastructure connectivity

### ingestion/ service
- `test_config.py` — config loading
- `test_embeddings_provider_routing.py` — embedding provider selection
- `test_ingestion_chunker.py` — document chunking
- `test_ingestion_dlq.py` — Dead Letter Queue handling
- `test_ingestion_embedder.py` — embedding generation
- `test_ingestion_parsers.py` — document parsing (PDF, HL7, TXT)
- `test_llm_router.py` — LLM provider routing
- `test_ingestion_*_end_to_end.py` — integration tests

### vector-store/ service
- `test_qdrant_store.py` — Qdrant backend
- `test_weaviate_schema.py` — Weaviate schema
- `test_weaviate_search_delete.py` — Weaviate search/delete
- `test_vector_store_factory.py` — store factory
- `test_dual_write_store.py` — dual-write wrapper
- `test_vector_store_layer.py` — end-to-end vector operations

### rag-engine/ service
- `test_query_embedder.py` — query embedding
- `test_rag_synthesizer.py` — LLM synthesis
- `test_retriever.py` — retrieval logic
- `test_rag_query_pipeline.py` — full RAG pipeline

### embedding-server/ service
- `test_clinical_bert_embedder.py` — clinical BERT model
- `test_hf_deploy_script.py` — deployment script
- `test_logging.py` — logging setup

### shared/
- `test_db_models.py` — database models (used by multiple services)

## pytest.ini per Service

Each service's `pytest.ini` should:
- Set `pythonpath` to include the service's src directory
- Register service-specific markers (e.g., `@pytest.mark.ingestion`)
- Configure test discovery to only look in `tests/`
- Set up logging for that service

Example for `ingestion/pytest.ini`:
```ini
[pytest]
pythonpath = .
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    ingestion: mark test as ingestion service test
    slow: mark test as slow
    integration: mark test as integration test
asyncio_mode = auto
log_cli = true
log_level = DEBUG
```

## Running Tests by Service

```bash
# From repo root, run tests for ONE service
cd api-gateway && pytest
cd ingestion && pytest
cd vector-store && pytest
cd rag-engine && pytest

# Or from repo root with pytest plugins:
pytest api-gateway/tests -v
pytest ingestion/tests -v
pytest vector-store/tests -v
pytest rag-engine/tests -v

# Run specific test category
pytest ingestion/tests/unit -v
pytest ingestion/tests/integration -v

# Run with specific marker
pytest -m ingestion -v
```

## CI/CD Integration

In GitHub Actions (`.github/workflows/ci.yml`), run tests per service:
```yaml
jobs:
  test-api-gateway:
    working-directory: api-gateway
    run: pytest tests
    
  test-ingestion:
    working-directory: ingestion
    run: pytest tests
    
  test-vector-store:
    working-directory: vector-store
    run: pytest tests
    
  test-rag-engine:
    working-directory: rag-engine
    run: pytest tests
```

## Migration Steps

1. **Create service-level test directories**
   ```
   mkdir -p api-gateway/tests/{unit,integration}
   mkdir -p ingestion/tests/{unit,integration}
   mkdir -p vector-store/tests/{unit,integration}
   mkdir -p rag-engine/tests/{unit,integration}
   mkdir -p embedding-server/tests/unit
   mkdir -p tests/shared
   ```

2. **Move test files** to appropriate service directories

3. **Create service-specific conftest.py** files
   - Simpler than current root conftest
   - Only register fixtures needed by that service
   - No sys.path manipulation needed

4. **Create pytest.ini** per service

5. **Simplify root conftest.py** (keep only shared fixtures if needed)

6. **Update CI/CD** to run tests per service

7. **Update developer documentation** (README, contributing guide)

## Benefits

✅ Clear service boundaries  
✅ No more sys.path hacks  
✅ Tests run with correct venv  
✅ Faster CI (services can run in parallel)  
✅ Easier debugging (which service failed?)  
✅ Easier to add new services  
✅ Better IDE support (no path confusion)  
✅ Dependency management per service  

## Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| Breaking cross-service tests | Keep `tests/shared/` for integration tests that need multiple services |
| Developer confusion during migration | Add clear docs and example commands |
| CI becomes more complex | Use pytest plugins or a test orchestrator script |
| Duplication of fixtures | Create shared fixture library (e.g., `tests/shared/fixtures.py`) |

## Implementation Order

1. Create directories structure (non-breaking)
2. Create service-level conftest + pytest.ini files
3. Move tests one service at a time (keep old tests until all moved)
4. Update CI/CD
5. Delete old `tests/` directory
6. Update documentation

