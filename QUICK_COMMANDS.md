# Quick Commands Reference

## Run Tests

### API Gateway (56 passing ✓)
```bash
cd api-gateway
pytest tests              # All tests
pytest tests/unit       # Unit tests only
pytest tests -v         # Verbose
pytest tests -q         # Quiet
```

### Ingestion
```bash
cd ingestion
pytest tests
pytest tests/unit
pytest tests/integration
```

### Vector Store
```bash
cd vector-store
pytest tests
pytest tests/unit
pytest tests/integration
```

### RAG Engine
```bash
cd rag-engine
pytest tests
pytest tests/unit
pytest tests/integration
```

### Embedding Server
```bash
cd embedding-server
pytest tests
pytest tests/unit
```

## Run All Services

```bash
# Sequential (safe, clear output)
for svc in api-gateway ingestion vector-store rag-engine embedding-server; do
    echo "Testing $svc..."
    cd $svc && pytest tests -q && cd ..
done

# Or manually
cd api-gateway && pytest tests -q
cd ../ingestion && pytest tests -q
cd ../vector-store && pytest tests -q
cd ../rag-engine && pytest tests -q
cd ../embedding-server && pytest tests -q
```

## Setup Service (First Time)

```bash
cd <service>
python -m venv venv
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate     # Windows
pip install -r requirements.txt
pytest tests
```

## Common Test Options

```bash
# Verbose output
pytest tests -v

# Very verbose
pytest tests -vv

# Quiet (summary only)
pytest tests -q

# Short traceback
pytest tests --tb=short

# Show print statements
pytest tests -s

# Stop on first failure
pytest tests -x

# Run matching tests
pytest tests -k "auth"

# Run specific test file
pytest tests/unit/test_auth_middleware.py

# Run specific test class
pytest tests/unit/test_auth_middleware.py::TestExtractRole

# Run specific test method
pytest tests/unit/test_auth_middleware.py::TestExtractRole::test_picks_highest_priority_role_when_multiple_present

# Collect only (no execution)
pytest tests --collect-only

# Parallel execution (requires pytest-xdist)
pytest tests -n auto
```

## Test Markers

```bash
# Run only unit tests
pytest tests -m unit

# Run only integration tests
pytest tests -m integration

# Skip slow tests
pytest tests -m "not slow"

# Run specific markers (service-dependent)
pytest api-gateway/tests -m auth
pytest ingestion/tests -m embeddings
pytest vector-store/tests -m qdrant
```

## Migration

### Migrate All Services at Once
```bash
cd /repo/root
python scripts/copy_and_update_ingestion_tests.py
python scripts/copy_and_update_vector_store_tests.py
python scripts/copy_and_update_rag_engine_tests.py
python scripts/copy_and_update_embedding_server_tests.py
```

### Or use batch script
```bash
.\scripts\migrate_all_services.ps1
```

## Coverage

```bash
# Install pytest-cov
pip install pytest-cov

# Run with coverage
pytest tests --cov=src --cov-report=html

# View report
# Open htmlcov/index.html
```

## Watch Mode (Auto-rerun)

```bash
# Install pytest-watch
pip install pytest-watch

# Run tests on file changes
ptw tests

# Run with verbose output
ptw tests -- -v
```

## Debugging

```bash
# Drop into debugger on failure
pytest tests -pdb

# Drop into debugger at start
pytest tests -pdbcls=IPython.terminal.debugger:TerminalPdb

# Print output (normally captured)
pytest tests -s

# Very verbose debugging
pytest tests -vv -s
```

## CI/CD Parallel Execution

```bash
# In .github/workflows/ci.yml, run services in parallel:

jobs:
  test-api-gateway:
    runs-on: ubuntu-latest
    steps:
      - run: cd api-gateway && pip install -r requirements.txt
      - run: cd api-gateway && pytest tests

  test-ingestion:
    runs-on: ubuntu-latest
    steps:
      - run: cd ingestion && pip install -r requirements.txt
      - run: cd ingestion && pytest tests

  # ... same pattern for other services
```

## Environment Setup

### Activate Venv (All Services)

```bash
# api-gateway
source venv-api-gateway/bin/activate       # macOS/Linux
# venv-api-gateway\Scripts\activate        # Windows

# ingestion
source venv-ingestion/bin/activate         # macOS/Linux
# venv-ingestion\Scripts\activate          # Windows

# etc...
```

### Install Dependencies (All Services)

```bash
cd api-gateway && pip install -r requirements.txt
cd ../ingestion && pip install -r requirements.txt
cd ../vector-store && pip install -r requirements.txt
cd ../rag-engine && pip install -r requirements.txt
cd ../embedding-server && pip install -r requirements.txt
```

## Troubleshooting

### Tests not found
```bash
# Make sure you're in the service directory
pwd  # should show api-gateway, ingestion, etc.

# Verify pytest.ini is present
ls pytest.ini

# Check test discovery
pytest --collect-only
```

### ModuleNotFoundError
```bash
# Ensure venv is activated
which python  # should show venv path

# Reinstall requirements
pip install -r requirements.txt

# Check sys.path
python -c "import sys; print('\n'.join(sys.path))"
```

### Slow tests
```bash
# Run only unit tests (no external deps)
pytest tests/unit

# Run in parallel
pytest tests -n auto
```

## One-Liners

```bash
# Test all services sequentially
for s in api-gateway ingestion vector-store rag-engine embedding-server; do (cd $s && pytest tests -q) || exit 1; done

# Test api-gateway only
cd api-gateway && pytest tests -q

# Test with coverage
cd api-gateway && pytest tests --cov=src

# Run single test
cd api-gateway && pytest tests/unit/test_auth_middleware.py::TestExtractRole::test_admin_outranks_everything

# Run and stop on first failure
cd api-gateway && pytest tests -x

# Run in parallel
cd api-gateway && pytest tests -n auto
```

## Help

```bash
# Pytest help
pytest --help

# Show fixtures
pytest --fixtures

# Show markers
pytest --markers

# Show plugins
pytest --version

# Run with verbose output and stop on failure
pytest tests -vv -x
```

---

**See also:**
- TESTING_QUICK_START.md (full quick reference)
- TESTING.md (complete guide)
- TEST_STRUCTURE_REFERENCE.txt (lookup card)
