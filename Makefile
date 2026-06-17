.PHONY: dev dev-lite stop logs migrate migration seed \
        setup-vector-stores kafka-topics vault-init \
        test test-unit test-integration test-load \
        lint format clean deploy-dev help

# ── Variables ────────────────────────────────────────────────────────────────
PYTHON   := python3
PIP      := pip
PYTEST   := pytest
RUFF     := ruff
MYPY     := mypy
COV_MIN  := 60

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  PatientVectorHub — Developer Makefile"
	@echo "  ────────────────────────────────────────────────────────────────"
	@echo "  make dev                Start full local stack (8 services)"
	@echo "  make dev-lite           Start minimal stack (Postgres+Redis+Weaviate+Kafka+Vault)"
	@echo "  make stop               Stop all containers"
	@echo "  make logs               Tail all container logs"
	@echo ""
	@echo "  make migrate            Run Alembic upgrade head"
	@echo "  make migration          Create new Alembic migration (prompts for message)"
	@echo "  make seed               Load synthetic test data"
	@echo "  make setup-vector-stores  Create Weaviate + Qdrant tenant schemas"
	@echo "  make kafka-topics       Create all Kafka topics"
	@echo "  make vault-init         Seed Vault with dev secrets"
	@echo ""
	@echo "  make test               Run full test suite (unit + integration)"
	@echo "  make test-unit          Run unit tests only (fast)"
	@echo "  make test-integration   Run integration tests (requires running stack)"
	@echo "  make test-load          Run Locust load tests"
	@echo "  make lint               Run ruff + mypy + eslint"
	@echo "  make format             Auto-format all code"
	@echo "  make clean              Remove containers and local volumes"
	@echo ""

# ── Local Dev Stack ───────────────────────────────────────────────────────────
dev:
	@echo "▶ Starting full PatientVectorHub stack..."
	docker compose up -d
	@echo "⏳ Waiting for services to be healthy (up to 90s)..."
	@sleep 10
	@$(MAKE) _wait-healthy
	@echo ""
	@echo "✅ All services healthy. Running setup..."
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) setup-vector-stores
	@$(MAKE) seed
	@echo ""
	@echo "  ┌─────────────────────────────────────────────────┐"
	@echo "  │  PatientVectorHub — Local Stack Ready            │"
	@echo "  │                                                  │"
	@echo "  │  FastAPI  → http://localhost:8000/health         │"
	@echo "  │  Weaviate → http://localhost:8080                │"
	@echo "  │  Qdrant   → http://localhost:6333                │"
	@echo "  │  Vault    → http://localhost:8200                │"
	@echo "  │  Keycloak → http://localhost:8443                │"
	@echo "  │  Kafka    → localhost:9092                       │"
	@echo "  │  Redis    → localhost:6379                       │"
	@echo "  │  Embed    → http://localhost:8001                │"
	@echo "  └─────────────────────────────────────────────────┘"
	@echo ""

dev-lite:
	@echo "▶ Starting minimal stack (Postgres, Redis, Weaviate, Kafka, Vault)..."
	docker compose up -d postgres redis weaviate kafka vault
	@echo "⏳ Waiting for services..."
	@sleep 8
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) seed
	@echo "✅ Lite stack ready (Keycloak + Qdrant + Embedding skipped)"

_wait-healthy:
	@for svc in pvh-postgres pvh-redis pvh-weaviate pvh-vault pvh-kafka; do \
	  echo "  Checking $$svc..."; \
	  for i in $$(seq 1 18); do \
	    status=$$(docker inspect --format='{{.State.Health.Status}}' $$svc 2>/dev/null || echo 'unknown'); \
	    if [ "$$status" = "healthy" ]; then echo "  ✓ $$svc"; break; fi; \
	    if [ $$i -eq 18 ]; then echo "  ✗ $$svc not healthy after 90s"; exit 1; fi; \
	    sleep 5; \
	  done; \
	done

stop:
	docker compose down
	@echo "✅ All containers stopped"

clean:
	docker compose down -v --remove-orphans
	@echo "✅ Containers, networks, and volumes removed"

logs:
	docker compose logs -f --tail=50

logs-%:
	docker compose logs -f --tail=100 $*

# ── Database ─────────────────────────────────────────────────────────────────
migrate:
	@echo "▶ Running Alembic migrations..."
	cd api-gateway && $(PYTHON) -m alembic upgrade head
	@echo "✅ Migrations applied"

migration:
	@read -p "Migration message: " msg; \
	cd api-gateway && $(PYTHON) -m alembic revision --autogenerate -m "$$msg"

migration-history:
	cd api-gateway && $(PYTHON) -m alembic history --verbose

migration-rollback:
	cd api-gateway && $(PYTHON) -m alembic downgrade -1
	@echo "✅ Rolled back one migration"

seed:
	@echo "▶ Seeding synthetic test data..."
	$(PYTHON) scripts/seed_data.py
	@echo "✅ Seed complete: 2 tenants, 4 users each, 1000 patients each"

# ── Infrastructure Setup ──────────────────────────────────────────────────────
setup-vector-stores:
	@echo "▶ Creating Weaviate + Qdrant schemas for all tenants..."
	$(PYTHON) scripts/setup_weaviate_schema.py
	$(PYTHON) scripts/setup_qdrant_schema.py
	@echo "✅ Vector store schemas created"

kafka-topics:
	@echo "▶ Creating Kafka topics..."
	$(PYTHON) scripts/create_kafka_topics.py
	@echo "✅ Kafka topics created"

vault-init:
	@echo "▶ Initialising Vault dev secrets..."
	bash scripts/vault_init.sh
	@echo "✅ Vault initialised"

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	@echo "▶ Running full test suite..."
	$(PYTEST) tests/ -x --cov=src --cov-fail-under=$(COV_MIN) \
	  --cov-report=term-missing -q
	@echo "✅ Tests passed"

test-unit:
	@echo "▶ Running unit tests..."
	$(PYTEST) tests/unit/ -v --tb=short
	@echo "✅ Unit tests passed"

test-integration:
	@echo "▶ Running integration tests (requires running stack)..."
	$(PYTEST) tests/integration/ -v --tb=short -m integration

test-rls:
	@echo "▶ Running RLS isolation tests (HIPAA gate)..."
	$(PYTEST) tests/integration/test_rls.py -v
	@echo "✅ RLS isolation verified"

test-load:
	@echo "▶ Running Locust load tests (50 users, 5 minutes)..."
	locust -f tests/load/ingest_load.py --headless \
	  -u 50 -r 5 -t 5m \
	  --host http://localhost:8000 \
	  --html tests/load/report.html
	@echo "✅ Load test complete — see tests/load/report.html"

test-e2e:
	@echo "▶ Running Playwright E2E tests..."
	cd dashboard && npx playwright test
	@echo "✅ E2E tests passed"

# ── Code Quality ─────────────────────────────────────────────────────────────
lint:
	@echo "▶ Linting Python..."
	$(RUFF) check .
	$(MYPY) api-gateway/src ingestion/src rag-engine/src vector-store/src \
	  --ignore-missing-imports
	@echo "▶ Linting TypeScript..."
	cd dashboard && npx eslint src/ --ext .ts,.tsx --max-warnings 0
	@echo "✅ Lint passed"

format:
	@echo "▶ Formatting Python..."
	$(RUFF) format .
	@echo "▶ Formatting TypeScript..."
	cd dashboard && npx prettier --write "src/**/*.{ts,tsx,css}"
	@echo "✅ Format complete"

# ── Deployment ────────────────────────────────────────────────────────────────
deploy-dev:
	@echo "▶ Deploying to dev cluster..."
	helm upgrade --install pvh-app ./infra/helm/pvh-app \
	  -f ./infra/helm/values/dev.yaml \
	  --namespace pvh-app \
	  --create-namespace \
	  --atomic \
	  --timeout 5m \
	  --wait
	@echo "✅ Deployed to dev"

# ── API Development ───────────────────────────────────────────────────────────
run-api:
	@echo "▶ Starting FastAPI dev server..."
	cd api-gateway && uvicorn src.main:app --reload --port 8000 \
	  --log-level debug

run-workers:
	@echo "▶ Starting Celery workers..."
	cd ingestion && celery -A src.workers.batch_worker.celery_app worker \
	  --loglevel=info --queues=doc-ingest -c 4

run-beat:
	@echo "▶ Starting Celery beat scheduler..."
	cd ingestion && celery -A src.workers.scheduled_tasks.celery_app beat \
	  --loglevel=info
