# Testing Guide — Service-Based Organization

This project organizes tests by service, with each service having its own test suite and venv.

## Directory Structure

```
api-gateway/
├── tests/
│   ├── unit/          # Unit tests (no external dependencies)
│   ├── integration/   # Integration tests (requires docker-compose)
│   └── conftest.py
├── conftest.py        # IDE discovery
└── pytest.ini

ingestion/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── conftest.py
└── pytest.ini

vector-store/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── conftest.py
└── pytest.ini

rag-engine/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── conftest.py
└── pytest.ini

embedding-server/
├── tests/
│   └── unit/
├── conftest.py
└── pytest.ini

tests/
├── shared/            # Cross-service integration tests
│   └── conftest.py
└── pytest.ini
```

## Running Tests

### Test a Single Service

Each service has its own requirements and venv. Run tests from the service directory:

```bash
# API Gateway tests
cd api-gateway
pytest tests                    # All tests
pytest tests/unit              # Unit tests only
pytest tests/integration       # Integration tests only
pytest tests -m unit           # By marker
pytest tests -k "auth"         # By name pattern

# Ingestion tests
cd ../ingestion
pytest tests
pytest tests -m integration

# Vector Store tests
cd ../vector-store
pytest tests

# RAG Engine tests
cd ../rag-engine
pytest tests
```

### Run All Service Tests (from repo root)

```bash
# Run tests in each service sequentially
for service in api-gateway ingestion vector-store rag-engine embedding-server; do
    echo "Testing $service..."
    cd "$service"
    pytest tests
    cd ..
done
```

Or use a simple script:

```bash
# tests/run_all_services.sh
#!/bin/bash
set -e
for service in api-gateway ingestion vector-store rag-engine embedding-server; do
    echo "━━━ Testing $service ━━━"
    (cd "$service" && pytest tests)
done
echo "✅ All services passed"
```

### Run Tests by Category

```bash
# Unit tests only (no external dependencies)
pytest api-gateway/tests -m unit
pytest ingestion/tests -m unit
pytest vector-store/tests -m unit

# Integration tests (requires docker-compose up)
pytest api-gateway/tests -m integration
pytest ingestion/tests -m integration

# Slow tests
pytest -m slow

# Specific test class
pytest api-gateway/tests/unit/test_auth_middleware.py::TestAuth
```

### Parallel Execution

Use `pytest-xdist` to run tests in parallel:

```bash
# Install: pip install pytest-xdist

cd api-gateway
pytest tests -n auto              # Use all available CPU cores
pytest tests -n 4                 # Use 4 workers

# Or use pytest-parallel plugin
pip install pytest-parallel
pytest tests --tests-per-worker auto
```

## Service Test Markers

### api-gateway
- `@pytest.mark.unit` — Unit tests (FastAPI app without network)
- `@pytest.mark.integration` — Integration tests (requires DB, Kafka, Vault)
- `@pytest.mark.auth` — Authentication/authorization tests
- `@pytest.mark.db` — Database/RLS tests

### ingestion
- `@pytest.mark.unit` — Unit tests
- `@pytest.mark.integration` — End-to-end document processing
- `@pytest.mark.parser` — Document parsing (PDF, HL7, TXT)
- `@pytest.mark.embeddings` — Embedding generation
- `@pytest.mark.chunker` — Text chunking
- `@pytest.mark.dlq` — Dead Letter Queue handling

### vector-store
- `@pytest.mark.unit` — Unit tests
- `@pytest.mark.integration` — Live Weaviate/Qdrant tests
- `@pytest.mark.weaviate` — Weaviate-specific tests
- `@pytest.mark.qdrant` — Qdrant-specific tests
- `@pytest.mark.dual_write` — Dual-write wrapper tests

### rag-engine
- `@pytest.mark.unit` — Unit tests
- `@pytest.mark.integration` — Full pipeline tests
- `@pytest.mark.retrieval` — Retrieval tests
- `@pytest.mark.synthesis` — LLM synthesis tests

## Environment Setup

Each service has its own venv and requirements file. Follow the setup for each service:

### api-gateway

```bash
cd api-gateway
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
pytest tests
```

### ingestion

```bash
cd ingestion
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests
```

### vector-store

```bash
cd vector-store
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests
```

### rag-engine

```bash
cd rag-engine
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests
```

## Running Integration Tests

Integration tests require the full stack running via docker-compose:

```bash
# Start the full stack
docker-compose up -d

# Wait for services to be healthy
docker-compose ps

# Run integration tests
cd api-gateway && pytest tests -m integration
cd ../ingestion && pytest tests -m integration
cd ../vector-store && pytest tests -m integration
```

## Writing New Tests

### New Unit Test for a Service

Create the test in the appropriate service directory:

```python
# api-gateway/tests/unit/test_my_feature.py

import pytest

class TestMyFeature:
    def test_something(self):
        from src.my_module import my_function
        result = my_function()
        assert result == expected
```

No sys.path manipulation needed — the service's `pytest.ini` handles it.

### New Integration Test

```python
# ingestion/tests/integration/test_e2e.py

import pytest

@pytest.mark.integration
class TestEndToEnd:
    async def test_document_processing(self, mock_kafka):
        from src.workers import process_document
        result = await process_document(...)
        assert result.success
```

### Using Fixtures

Each service's conftest provides relevant fixtures:

```python
# api-gateway/tests/unit/test_query.py

def test_query_endpoint(client, mock_vault):
    """client and mock_vault come from api-gateway/tests/conftest.py"""
    response = client.get("/query")
    assert response.status_code == 200
```

## CI/CD Integration

The GitHub Actions workflow runs tests per service:

```yaml
# .github/workflows/ci.yml

jobs:
  test-api-gateway:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: cd api-gateway && pip install -r requirements.txt
      - run: cd api-gateway && pytest tests

  test-ingestion:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: cd ingestion && pip install -r requirements.txt
      - run: cd ingestion && pytest tests
      
  # ... similar for vector-store, rag-engine
```

Services can run in parallel in CI for faster feedback.

## Troubleshooting

### "ModuleNotFoundError: No module named 'src'"

Ensure you're running pytest from the service directory, and the service's venv is activated:

```bash
cd api-gateway
source venv/bin/activate  # or venv\Scripts\activate
pytest tests
```

### "No tests ran"

Check that pytest can find tests:

```bash
pytest tests --collect-only       # List all tests that would run
pytest tests -v                   # Run with verbose output
```

### "Import errors in fixtures"

If a fixture fails to import, check that the venv is activated and requirements are installed:

```bash
pip list | grep -i pytest         # Should see pytest installed
```

### Cross-service import failing

If you're writing a test that needs to import from another service (e.g., RAG engine needs vector_store), ensure both services are in the path. Check the relevant service's `conftest.py`:

```python
# rag-engine/conftest.py already includes vector-store path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "vector-store", "src"))
```

### Test isolation issues

Each test file is run in a fresh Python interpreter. If tests are interfering with each other:

1. Check for global state modifications
2. Use proper pytest fixtures (not globals)
3. Use `@pytest.fixture(autouse=True)` to reset state before each test

## Best Practices

### ✅ Do
- Use service-specific directories for tests
- Run tests from the service directory with that venv active
- Use pytest markers to categorize tests
- Mock external dependencies in unit tests
- Keep unit tests fast (< 1s each)
- Isolate integration tests from unit tests

### ❌ Don't
- Run tests from repo root without specifying service
- Mix tests from multiple services in one test file
- Put all tests in a single file (organize by feature)
- Use global mocks that affect other tests
- Skip test isolation in integration tests

## FAQ

**Q: Can I run tests from the repo root?**
A: You need to specify which service: `pytest api-gateway/tests`. Different services have different requirements, so running all together requires all venvs activated, which isn't practical.

**Q: How do I add a new service?**
A: Create `<service>/tests/`, `<service>/conftest.py`, and `<service>/pytest.ini`. Copy the structure from an existing service.

**Q: Can unit tests import from multiple services?**
A: Avoid it. Each unit test should test one service in isolation. Use integration tests for cross-service scenarios.

**Q: How do I debug a failing test?**
A: Use `pytest -vv tests/<test_file> --tb=long` for detailed output, or add `import pdb; pdb.set_trace()` to the test.

**Q: Why are my async tests failing?**
A: Make sure `pytest-asyncio` is installed and `asyncio_mode = auto` is in `pytest.ini`.

