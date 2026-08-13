# Test Failure Analysis & Resolution

## Summary

**All 22 test failures are due to missing Docker services, NOT code bugs.** Integration tests require a running Docker Compose stack.

---

## Failure Breakdown

### PostgreSQL Connection Failures (16 tests)
- **Tests:** RLS isolation, core tables isolation, postgres connectivity
- **Error:** `ConnectionRefusedError: [WinError 1225] The remote computer refused the network connection`
- **Service:** PostgreSQL on localhost:5432
- **Fix:** Start with `docker-compose up postgres -d`

### Redis Connection Failures (2 tests)
- **Tests:** `TestRedisConnectivity::test_redis_reachable`, `test_redis_set_get`
- **Error:** `redis.exceptions.ConnectionError: Error 10061 connecting to localhost:6379`
- **Service:** Redis on localhost:6379
- **Fix:** Start with `docker-compose up redis -d`

### Vault Connection Failures (2 tests)
- **Tests:** `TestVaultConnectivity::test_vault_reachable`, `test_vault_dev_token_works`
- **Error:** `httpx.ConnectError` / `requests.exceptions.ConnectionError`
- **Service:** Vault on localhost:8200
- **Fix:** Start with `docker-compose up vault -d`

### Weaviate Connection Failures (2 tests)
- **Tests:** `TestWeaviateConnectivity::test_weaviate_ready`, `test_weaviate_tenant_collection_exists`
- **Error:** `weaviate.exceptions.WeaviateConnectionError: timed out`
- **Service:** Weaviate on localhost:8080
- **Fix:** Start with `docker-compose up weaviate -d`

---

## What Passed

✅ **2 tests skipped** — These are likely environment checks that gracefully skip when services are unavailable.

---

## Root Cause Analysis

### Why Integration Tests Fail Without Docker

Each integration test opens a real connection to external services:

```python
# From test_stack_connectivity.py
async def test_postgres_reachable(self):
    import asyncpg
    conn = await asyncpg.connect(POSTGRES_URL)  # ← Tries to connect to real DB
    # ...
```

```python
# From test_rls_isolation.py
conn = await asyncpg.connect(POSTGRES_URL)  # ← Real PostgreSQL connection required
```

These are **not mocked or stubbed** — they test against real services. This is correct behavior for integration tests.

---

## Quick Start: Make the Tests Pass

### Step 1: Start Docker Services
```bash
cd a:\PatientVectorHub
docker-compose up -d
```

**Wait 20-30 seconds** for services to become healthy (especially Weaviate).

### Step 2: Verify Services Are Running
```bash
docker-compose ps
```

You should see all services with status `(healthy)` or `Up`:
```
NAME                 STATUS
pvh-postgres         Up (healthy)
pvh-redis            Up (healthy)
pvh-weaviate         Up (healthy)
pvh-vault            Up (healthy)
pvh-kafka            Up (healthy)
pvh-qdrant           Up (healthy)
pvh-keycloak         Up (healthy)
```

### Step 3: Run Tests
```bash
cd api-gateway
pytest tests/integration/ -v
```

Or use the helper script:
```bash
.\run_tests.ps1 integration  # PowerShell
run_tests.bat integration    # cmd
```

---

## For Different Testing Scenarios

### Scenario 1: I Want to Run Only Unit Tests (No Docker)
```bash
cd api-gateway
pytest tests/unit/ -v -m unit
```

Unit tests don't require Docker and should all pass.

### Scenario 2: I Want to Run All Tests (With Docker)
```bash
cd a:\PatientVectorHub
docker-compose up -d
sleep 30  # Wait for services to be ready
cd api-gateway
pytest -v
```

### Scenario 3: I'm in a CI/CD Pipeline
The `.github/workflows/ci.yml` already handles:
1. Starting Docker services
2. Waiting for health checks
3. Running all tests
4. Stopping services

No changes needed.

### Scenario 4: I Want to Run Tests in Watch Mode
```bash
pip install pytest-watch
cd api-gateway
ptw tests/unit/  # Watch unit tests
```

---

## Understanding the Test Structure

All integration tests are marked with `@pytest.mark.integration`:

```python
# test_rls_isolation.py
pytestmark = pytest.mark.integration

class TestRLSPolicyExists:
    async def test_rls_enabled_on_patients(self):
        # Requires PostgreSQL
```

This allows selective running:
- `pytest -m unit` → Only unit tests
- `pytest -m integration` → Only integration tests
- `pytest` → All tests

---

## Docker Compose Service Quick Reference

| Service | Port | Status Check | Start Time | Purpose |
|---------|------|--------------|-----------|---------|
| **PostgreSQL** | 5432 | `pg_isready` | ~5s | RLS tests, data store |
| **Redis** | 6379 | `redis-cli ping` | ~3s | Cache, task queue |
| **Vault** | 8200 | `vault status` | ~5s | Secrets management |
| **Weaviate** | 8080 | HTTP `/v1/.well-known/ready` | ~20s | Vector store (slow!) |
| **Kafka** | 9092 | Topic listing | ~30s | Event streaming |
| **Qdrant** | 6333 | HTTP `/healthz` | ~10s | Vector store backup |
| **Keycloak** | 8443 | HTTP realm endpoint | ~60s | Auth provider |

**Weaviate is the slowest to start (20-30s).** Wait for all services to show `(healthy)` status.

---

## Cleanup

### Stop All Services
```bash
docker-compose down
```

### Stop and Remove All Data
```bash
docker-compose down -v
```

### View Service Logs
```bash
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f weaviate
```

---

## Common Issues & Solutions

### Issue: "Connection refused" on port 5432
**Solution:** PostgreSQL is not running
```bash
docker-compose up postgres -d
docker-compose logs postgres  # Check for errors
```

### Issue: Tests pass sometimes, fail other times
**Possible causes:**
1. Services aren't fully healthy yet (wait 30s)
2. Port conflicts (check `docker ps` for duplicate services)
3. `.env` file not found (copy from `.env.example`)

**Solution:**
```bash
docker-compose down -v
docker-compose up -d
sleep 30
pytest -v
```

### Issue: Weaviate times out at 2-second timeout
**Reason:** Weaviate is legitimately slow to start (20-30s)
**Solution:** Wait longer and check its status
```bash
docker-compose logs weaviate  # Shows startup progress
docker-compose ps weaviate    # Should show "(healthy)"
```

### Issue: Keycloak not needed for API tests
**Note:** Keycloak (on port 8443) is optional for these tests
**You can skip it:**
```bash
# Don't include keycloak service
docker-compose up -d postgres redis vault weaviate kafka qdrant
```

---

## CI/CD: What GitHub Actions Does

The `.github/workflows/ci.yml` workflow:

1. ✅ Starts `docker-compose` services
2. ✅ Waits for health checks to pass
3. ✅ Runs `pytest tests/` (all tests, unit + integration)
4. ✅ Generates coverage reports
5. ✅ Stops services
6. ✅ Fails if any tests fail

**No manual intervention needed in CI.**

---

## Next Steps

1. **Start Docker services:**
   ```bash
   docker-compose up -d
   ```

2. **Wait 30 seconds** and verify all are healthy:
   ```bash
   docker-compose ps
   ```

3. **Run integration tests:**
   ```bash
   cd api-gateway
   pytest tests/integration/ -v
   ```

4. **Or run unit tests only** (no Docker needed):
   ```bash
   pytest tests/unit/ -v -m unit
   ```

All tests should now pass! 🎉

---

## References

- **Docker Compose:** `docker-compose.yml`
- **Environment:** `.env.example`
- **Unit Tests:** `tests/unit/`
- **Integration Tests:** `tests/integration/`
- **CI/CD:** `.github/workflows/ci.yml`
- **Test Guide:** `INTEGRATION_TESTS_GUIDE.md`
