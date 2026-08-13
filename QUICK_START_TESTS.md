# Quick Start: Running Tests

## ⚡ TL;DR — In 2 Minutes

### Option A: Run Unit Tests Only (No Docker Needed) ✨
```bash
cd api-gateway
pytest tests/unit/ -v
```
✅ Fast, no dependencies, tests pass in ~10s

---

### Option B: Run All Tests with Docker 🐳
```bash
# 1. From workspace root
docker-compose up -d
sleep 30

# 2. From api-gateway directory
pytest -v
```
✅ Takes ~2 minutes total (mostly Docker startup)

---

## 🎯 Choose Your Path

### 👤 "I'm developing locally and don't need integration tests"
```bash
cd api-gateway
pytest tests/unit/ -v -m unit
```
This runs fast (10-20s) and doesn't require Docker.

### 🔧 "I need to test the full stack"
```bash
# From repo root
docker-compose up -d
sleep 30

# Check services are healthy
docker-compose ps

# Then run all tests
cd api-gateway
pytest -v
```

### 🚀 "I want to use helper scripts"
**PowerShell (Windows):**
```powershell
cd api-gateway
.\run_tests.ps1 unit          # Unit tests only
.\run_tests.ps1 integration   # Integration tests (requires Docker)
.\run_tests.ps1 all           # All tests
```

**Command Prompt (Windows):**
```cmd
cd api-gateway
run_tests.bat unit
run_tests.bat integration
run_tests.bat all
```

---

## 📋 Checklist

### Before Running Integration Tests

- [ ] Docker installed and running
- [ ] From repo root: `docker-compose up -d`
- [ ] Wait 30 seconds
- [ ] Verify: `docker-compose ps` shows all services healthy
- [ ] Environment file: `.env` exists (or copy from `.env.example`)
- [ ] From `api-gateway/`: `pytest tests/integration/ -v`

### Before Running Unit Tests

- [ ] Python 3.10+ installed
- [ ] Virtual environment activated: `venv-api-gateway`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] From `api-gateway/`: `pytest tests/unit/ -v`

---

## ✅ What Should Pass

### Unit Tests (Always Pass Without Docker)
- ✅ `tests/unit/test_auth_middleware.py`
- ✅ `tests/unit/test_db_models.py`
- ✅ `tests/unit/test_errors.py`
- ✅ `tests/unit/test_phase1_health.py`
- ✅ `tests/unit/test_query_router.py`
- ✅ `tests/unit/test_rbac.py`
- ✅ `tests/unit/test_seed_data.py`

### Integration Tests (Require Docker)
- ✅ `tests/integration/test_rls_isolation.py` (4 tests)
- ✅ `tests/integration/test_rls_isolation_core_tables.py` (9 tests)
- ✅ `tests/integration/test_stack_connectivity.py` (9 tests)

---

## 🔴 Test Failures = Services Down

All test failures in the provided output are from **missing Docker services**, NOT bugs:

| Error | Cause | Fix |
|-------|-------|-----|
| `ConnectionRefusedError: [WinError 1225]` | PostgreSQL not running | `docker-compose up postgres -d` |
| `redis.exceptions.ConnectionError` | Redis not running | `docker-compose up redis -d` |
| `httpx.ConnectError` (port 8200) | Vault not running | `docker-compose up vault -d` |
| `weaviate.exceptions.WeaviateConnectionError` | Weaviate not running | `docker-compose up weaviate -d` |

**Start all services:** `docker-compose up -d`

---

## 🐛 Debugging

### See what's running
```bash
docker-compose ps
```

### Check if a service is healthy
```bash
docker-compose logs postgres
docker-compose logs redis
docker-compose logs weaviate
```

### Restart everything fresh
```bash
docker-compose down -v
docker-compose up -d
sleep 30
```

### Run a single test with verbose output
```bash
pytest tests/unit/test_auth_middleware.py::TestAuthMiddleware::test_validate_jwt -vvs
```

---

## 📚 Full Documentation

- **Detailed guide:** `INTEGRATION_TESTS_GUIDE.md`
- **Failure analysis:** `TEST_FAILURE_ANALYSIS.md`
- **Docker setup:** `docker-compose.yml`

---

## ⚡ Pro Tips

### Tip 1: Watch mode (requires pytest-watch)
```bash
pip install pytest-watch
ptw tests/unit/           # Rerun on file changes
```

### Tip 2: Run with coverage
```bash
pytest --cov=src tests/ --cov-report=html
# Open htmlcov/index.html
```

### Tip 3: Skip slow tests
```bash
pytest -m "not slow" -v
```

### Tip 4: Run tests matching a pattern
```bash
pytest -k "test_rls" -v           # Only RLS tests
pytest -k "not integration" -v    # Skip integration tests
```

---

## 🎓 Understanding the Output

### When tests pass ✅
```
tests/unit/test_auth_middleware.py::TestAuthMiddleware::test_validate_jwt PASSED
tests/unit/test_rbac.py::TestRBAC::test_check_permission PASSED
========================= 7 passed in 0.42s =========================
```

### When services are down ❌
```
tests/integration/test_stack_connectivity.py::TestPostgresConnectivity::test_postgres_reachable FAILED
E   ConnectionRefusedError: [WinError 1225] The remote computer refused the network connection
========================= 1 failed in 2.34s ==========================
```
**→ This is expected. Start Docker services first.**

---

## 🚀 Next Step

Choose one:

**Quick unit tests (30 seconds):**
```bash
cd api-gateway
pytest tests/unit/ -v
```

**Full test suite (2 minutes):**
```bash
docker-compose up -d && sleep 30 && cd api-gateway && pytest -v
```

Both should work! 🎉
