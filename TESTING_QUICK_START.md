# Testing Quick Start Guide

## TL;DR — Run Tests

### For Each Service

```bash
# From repo root, test one service at a time
cd api-gateway && pytest tests                    # API Gateway
cd ../ingestion && pytest tests                   # Ingestion
cd ../vector-store && pytest tests                # Vector Store
cd ../rag-engine && pytest tests                  # RAG Engine
cd ../embedding-server && pytest tests            # Embedding Server
```

### Setup (First Time)

```bash
# Example: Setting up api-gateway tests
cd api-gateway

# Create venv
python -m venv venv

# Activate venv
source venv/bin/activate          # macOS/Linux
# or
venv\Scripts\activate             # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests
```

## Common Commands

| Command | What It Does |
|---------|-------------|
| `pytest tests` | Run all tests in service |
| `pytest tests/unit` | Run only unit tests |
| `pytest tests/integration` | Run only integration tests |
| `pytest tests -m unit -v` | Unit tests with verbose output |
| `pytest tests -k "auth"` | Run tests matching "auth" in name |
| `pytest tests --tb=short` | Show short traceback on failures |
| `pytest tests -x` | Stop on first failure |
| `pytest tests -n auto` | Run in parallel (needs `pytest-xdist`) |

## Test Structure Per Service

```
api-gateway/
├── tests/
│   ├── unit/           ← Fast tests, no external deps
│   ├── integration/    ← Slow tests, need docker-compose
│   └── conftest.py     ← Fixtures
├── conftest.py         ← IDE discovery
└── pytest.ini          ← Configuration
```

## Test Markers

Each service uses markers to organize tests:

```bash
# Unit tests only (fast, no external dependencies)
pytest tests -m unit

# Integration tests (requires docker-compose up)
pytest tests -m integration

# Service-specific markers
pytest api-gateway/tests -m auth              # Authentication tests
pytest ingestion/tests -m embeddings          # Embedding tests
pytest vector-store/tests -m qdrant           # Qdrant tests
```

## When Tests Fail

### Module Not Found Errors

```
ModuleNotFoundError: No module named 'src'
```

**Fix:** Make sure you're in the service directory with its venv activated:

```bash
cd api-gateway
source venv/bin/activate  # or venv\Scripts\activate
pytest tests
```

### Connection Errors (integration tests)

```
socket.gaierror: [Errno 11001] getaddrinfo failed
```

**Fix:** Start the services with docker-compose:

```bash
docker-compose up -d
pytest tests -m integration
```

### Missing Dependencies

```
ModuleNotFoundError: No module named 'celery'
```

**Fix:** Install the service's requirements:

```bash
pip install -r requirements.txt
```

## Directory Tree

Where tests go by service:

```
✅ api-gateway/tests/{unit,integration}/
✅ ingestion/tests/{unit,integration}/
✅ vector-store/tests/{unit,integration}/
✅ rag-engine/tests/{unit,integration}/
✅ embedding-server/tests/unit/
✅ tests/shared/ (for cross-service integration)
```

## Running Full Test Suite

```bash
# Option 1: Manually run each service
cd api-gateway && pytest tests && cd ..
cd ingestion && pytest tests && cd ..
# ... repeat for other services

# Option 2: Create a script (see TESTING.md for details)
bash tests/run_all.sh

# Option 3: Use pytest with service paths (from repo root)
pytest api-gateway/tests \
        ingestion/tests \
        vector-store/tests \
        rag-engine/tests \
        embedding-server/tests
```

## Writing a New Test

**Location:** `<service>/tests/{unit or integration}/test_<feature>.py`

**Template:**

```python
import pytest

class TestMyFeature:
    def test_something(self):
        """Describe what you're testing."""
        from src.my_module import my_function
        
        result = my_function()
        
        assert result == expected_value
        
    @pytest.mark.integration
    def test_something_with_external_service(self):
        """Test that needs docker-compose running."""
        # Your test here
        pass
```

**No sys.path manipulation needed** — the service's `pytest.ini` handles it.

## Pro Tips

### 🚀 Run tests faster with parallel execution

```bash
pip install pytest-xdist
pytest tests -n auto              # Use all CPU cores
```

### 📊 Generate coverage report

```bash
pip install pytest-cov
pytest tests --cov=src --cov-report=html
# Open htmlcov/index.html
```

### 🐛 Debug a failing test

```bash
pytest tests/unit/test_auth_middleware.py::TestAuth::test_login -vv
# or add to test:
import pdb; pdb.set_trace()
```

### 🔄 Watch tests (rerun on file save)

```bash
pip install pytest-watch
ptw tests          # Auto-rerun tests on changes
```

### 📝 Show print statements

```bash
pytest tests -s      # Show stdout
pytest tests -vv     # Very verbose
```

## Continuous Integration

Each service runs independently in CI:

```yaml
# .github/workflows/ci.yml
jobs:
  test-api-gateway:
    runs-on: ubuntu-latest
    steps:
      - run: cd api-gateway && pytest tests
      
  test-ingestion:
    runs-on: ubuntu-latest
    steps:
      - run: cd ingestion && pytest tests
      
  # ... similar for other services
```

Services can run in **parallel** for faster feedback.

## Next Steps

1. Read **TESTING.md** for the full guide
2. Read **TEST_REORGANIZATION_PLAN.md** for architecture details
3. Try: `cd api-gateway && pytest tests -m unit`
4. Update CI/CD if migrating from centralized tests

## Still Have Questions?

- **TESTING.md** — Comprehensive testing guide with examples and troubleshooting
- **TESTING_QUICK_START.md** — This file (quick reference)
- Service-specific guides — See each service's README

---

**Last Updated:** August 2026  
**Format:** Service-based test organization
