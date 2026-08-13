# Integration Tests Guide

## Problem
All integration tests are failing with connection refused errors because the required Docker services (PostgreSQL, Redis, Vault, Weaviate, etc.) are not running.

## Root Cause
Integration tests require a running Docker Compose stack. The test failures are **expected** when services are down — they're not code issues, but infrastructure dependency issues.

## Solution

### Option 1: Run Tests with Docker Services (Recommended)

**Start all services first:**
```bash
docker-compose up -d
```

**Wait for services to be healthy** (~20-30 seconds, especially Weaviate):
```bash
docker-compose ps
```

**Run all tests (unit + integration):**
```bash
pytest -v
```

**Run only integration tests:**
```bash
pytest tests/integration/ -v -m integration
```

**Run only unit tests** (no dependencies):
```bash
pytest tests/unit/ -v -m unit
```

---

### Option 2: Skip Integration Tests (Quick Local Development)

If you don't need integration tests right now, run only unit tests:

```bash
pytest tests/unit/ -v
```

This will skip all integration tests that require Docker services.

---

### Option 3: CI/CD Pipeline (GitHub Actions)

The `.github/workflows/ci.yml` handles starting services and running all tests automatically. See that file for the exact steps.

---

## Test Organization

Tests are organized by markers in `pytest.ini`:

- **`@pytest.mark.unit`** — Tests that don't require external services
  - Database models, error handling, schema validation, auth logic
  
- **`@pytest.mark.integration`** — Tests that require Docker services
  - RLS policy validation (PostgreSQL)
  - Redis connectivity
  - Vault connectivity
  - Weaviate connectivity
  - Stack health checks

All integration test files have `pytestmark = pytest.mark.integration` at the module level.

---

## Common Commands

| Task | Command |
|------|---------|
| Start Docker services | `docker-compose up -d` |
| Stop Docker services | `docker-compose down` |
| View service status | `docker-compose ps` |
| View service logs | `docker-compose logs -f [service]` |
| Run all tests | `pytest -v` |
| Run only unit tests | `pytest -m unit -v` |
| Run only integration tests | `pytest -m integration -v` |
| Run specific test class | `pytest tests/unit/test_auth_middleware.py::TestAuthMiddleware -v` |
| Run with coverage | `pytest --cov=src tests/ -v` |

---

## Service Details

Docker Compose services required for integration tests:

| Service | Port | Health Check | Notes |
|---------|------|--------------|-------|
| PostgreSQL | 5432 | `pg_isready` | RLS tests, migrations |
| Redis | 6379 | `redis-cli ping` | Cache, task queue |
| Weaviate | 8080 | HTTP health endpoint | Vector store (slow to start) |
| Vault | 8200 | `vault status` | Secrets management |
| Kafka | 9092 | Topic listing | Message streaming |
| Qdrant | 6333 | HTTP health endpoint | Vector store (backup) |
| Keycloak | 8443 | HTTP endpoint | Authentication (if needed) |

---

## Troubleshooting

### Services won't start
```bash
docker-compose down -v  # Remove volumes
docker-compose up -d    # Fresh start
```

### PostgreSQL won't connect
- Check `DATABASE_URL` in `.env`
- Ensure port 5432 is not already in use
- Verify credentials: `pvh:pvh_local@localhost:5432/pvh`

### Weaviate takes too long
Weaviate has a `start_period: 20s` health check. It's normal to wait 20-30 seconds.

### Tests pass locally but fail in CI
- Ensure `.env.example` matches your local setup
- Check CI runs against `RLS_TEST_DATABASE_URL` (non-superuser role)
- See `.github/workflows/ci.yml` for exact CI setup

---

## Development Workflow

### For Quick Local Development (Unit Tests Only)
```bash
pytest tests/unit/ -v --tb=short
```

### For Full Integration Testing (Requires Docker)
```bash
docker-compose up -d
sleep 30  # Wait for services
pytest -v
```

### Pre-commit Hook (Optional)
Add this to `.git/hooks/pre-commit` to run unit tests before commits:
```bash
pytest tests/unit/ -v --tb=short
```

---

## See Also
- `docker-compose.yml` — Service definitions
- `.env.example` — Required environment variables
- `.github/workflows/ci.yml` — CI test pipeline
- `tests/integration/test_rls_isolation.py` — RLS test details
- `tests/integration/test_stack_connectivity.py` — Service connectivity tests
