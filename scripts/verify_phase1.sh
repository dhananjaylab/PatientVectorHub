#!/usr/bin/env bash
# scripts/verify_phase1.sh
# Phase 1 Definition-of-Done verification.
# All 5 gates must pass before Phase 2 begins.
# Usage: bash scripts/verify_phase1.sh
set -euo pipefail

PASS=0; FAIL=0
GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${NC} $1"; ((FAIL++)); }

echo ""
echo -e "${BOLD}PatientVectorHub — Phase 1 Definition of Done${NC}"
echo "────────────────────────────────────────────────────"

# Gate 1: docker compose containers healthy
echo ""
echo "Gate 1: Container health"
for svc in pvh-postgres pvh-redis pvh-weaviate pvh-vault pvh-kafka; do
  status=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "not_found")
  if [ "$status" = "healthy" ]; then
    pass "$svc is healthy"
  else
    fail "$svc status: $status (run: make dev)"
  fi
done

# Gate 2: Alembic migration
echo ""
echo "Gate 2: Database migration"
if cd api-gateway && python -m alembic current 2>&1 | grep -q "001"; then
  pass "Alembic migration 001 applied"
  cd ..
else
  cd .. 2>/dev/null || true
  fail "Migration not applied (run: make migrate)"
fi

# Gate 3: Seed data
echo ""
echo "Gate 3: Seed data"
if python3 -c "
import os, psycopg2
conn = psycopg2.connect(os.getenv('DATABASE_URL_SYNC', 'postgresql://pvh:pvh_local@localhost:5432/pvh').replace('+asyncpg','').replace('+psycopg2',''))
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM tenants')
t = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM patients')
p = cur.fetchone()[0]
conn.close()
assert t >= 2, f'Expected 2+ tenants, got {t}'
assert p >= 1000, f'Expected 1000+ patients, got {p}'
" 2>/dev/null; then
  pass "Seed data: 2 tenants, 1000+ patients"
else
  fail "Seed data missing (run: make seed)"
fi

# Gate 4: Unit tests
echo ""
echo "Gate 4: Unit tests"
if python3 -m pytest tests/unit/ -q --tb=no 2>/dev/null | tail -1 | grep -q "passed"; then
  result=$(python3 -m pytest tests/unit/ -q --tb=no 2>/dev/null | tail -1)
  pass "Unit tests: $result"
else
  fail "Unit tests failing (run: make test-unit)"
fi

# Gate 5: FastAPI /health
echo ""
echo "Gate 5: FastAPI /health endpoint"
if curl -sf http://localhost:8000/health 2>/dev/null | python3 -c "
import sys, json
body = json.load(sys.stdin)
assert body.get('status') == 'alive', f\"Expected 'alive', got {body}\"
" 2>/dev/null; then
  pass "/health returns {\"status\": \"alive\"}"
else
  fail "/health not responding (run: make run-api in another terminal)"
fi

# Summary
echo ""
echo "────────────────────────────────────────────────────"
TOTAL=$((PASS + FAIL))
if [ "$FAIL" -eq 0 ]; then
  echo -e "  ${GREEN}${BOLD}Phase 1 COMPLETE ✓${NC}  ($PASS/$TOTAL gates passed)"
  echo ""
  echo "  Next: Phase 2 — Database Foundation"
  echo "  Run:  make migration  (message: 'create core tables')"
else
  echo -e "  ${RED}${BOLD}Phase 1 INCOMPLETE${NC}  ($PASS/$TOTAL gates passed, $FAIL failed)"
  echo ""
  echo "  Fix failing gates, then re-run: bash scripts/verify_phase1.sh"
fi
echo ""
