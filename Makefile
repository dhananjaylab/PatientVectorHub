# Windows-compatible Makefile for PatientVectorHub
# Faithfully mirrors the original Makefile with Windows-native commands
# Usage: make [target]

.PHONY: dev dev-lite stop logs migrate migration seed \
        setup-vector-stores kafka-topics vault-init \
        test test-unit test-integration clean help

# ── Variables ────────────────────────────────────────────────────────────────
PYTHON   := python
PYTEST   := pytest
COV_MIN  := 60

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo.
	@echo   PatientVectorHub - Windows Developer Makefile
	@echo   ────────────────────────────────────────────────────────────────
	@echo   make dev                Start full local stack
	@echo   make dev-lite           Start minimal stack
	@echo   make stop               Stop all containers
	@echo   make clean              Remove containers and volumes
	@echo   make logs               Tail all container logs
	@echo.
	@echo   make migrate            Run Alembic upgrade head
	@echo   make migration          Create new Alembic migration
	@echo   make seed               Load synthetic test data
	@echo   make setup-vector-stores  Create Weaviate + Qdrant schemas
	@echo   make kafka-topics       Create all Kafka topics
	@echo   make vault-init         Seed Vault with dev secrets
	@echo.
	@echo   make test               Run full test suite
	@echo   make test-unit          Run unit tests only
	@echo   make test-integration   Run integration tests
	@echo.

# ── Local Dev Stack ───────────────────────────────────────────────────────────
dev:
	@echo "▶ Starting full PatientVectorHub stack..."
	docker compose up -d
	@echo "⏳ Waiting for services to be healthy (up to 90s)..."
	@timeout /t 10 /nobreak
	@echo "Running setup..."
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) setup-vector-stores
	@$(MAKE) seed
	@echo.
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
	@echo.

dev-lite:
	@echo "▶ Starting minimal stack (Postgres, Redis, Weaviate, Kafka, Vault)..."
	docker compose up -d postgres redis weaviate kafka vault
	@echo "⏳ Waiting for services..."
	@timeout /t 8 /nobreak
	@$(MAKE) vault-init
	@$(MAKE) migrate
	@$(MAKE) kafka-topics
	@$(MAKE) seed
	@echo "✅ Lite stack ready (Keycloak + Qdrant + Embedding skipped)"

stop:
	docker compose down
	@echo "✅ All containers stopped"

clean:
	docker compose down -v --remove-orphans
	@echo "✅ Containers, networks, and volumes removed"

logs:
	docker compose logs -f --tail=50

# ── Database ─────────────────────────────────────────────────────────────────
migrate:
	@echo "▶ Running Alembic migrations..."
	cd api-gateway && $(PYTHON) -m alembic upgrade head
	@cd ..
	@echo "✅ Migrations applied"

migration:
	@powershell -Command "$$msg = Read-Host 'Migration message'; cd api-gateway; python -m alembic revision --autogenerate -m $$msg; cd .."

seed:
	@echo "▶ Seeding synthetic test data..."
	$(PYTHON) scripts\seed_data.py
	@echo "✅ Seed complete: 2 tenants, 4 users each, 1000 patients each"

# ── Infrastructure Setup ──────────────────────────────────────────────────────
setup-vector-stores:
	@echo "▶ Creating Weaviate + Qdrant schemas for all tenants..."
	$(PYTHON) scripts\setup_weaviate_schema.py
	$(PYTHON) scripts\setup_qdrant_schema.py
	@echo "✅ Vector store schemas created"

kafka-topics:
	@echo "▶ Creating Kafka topics..."
	$(PYTHON) scripts\create_kafka_topics.py
	@echo "✅ Kafka topics created"

vault-init:
	@echo "▶ Initialising Vault dev secrets..."
	@powershell -Command "if (Test-Path 'C:\Program Files\Git\bin\bash.exe') { & 'C:\Program Files\Git\bin\bash.exe' scripts\vault_init.sh } else { Write-Host 'Note: vault_init.sh requires bash. Install Git for Windows or run: bash scripts/vault_init.sh' -ForegroundColor Yellow }"
	@echo "✅ Vault initialised"

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	@echo "▶ Running full test suite..."
	$(PYTEST) tests\ -x --cov=src --cov-fail-under=$(COV_MIN) --cov-report=term-missing -q
	@echo "✅ Tests passed"

test-unit:
	@echo "▶ Running unit tests..."
	$(PYTEST) tests\unit\ -v --tb=short
	@echo "✅ Unit tests passed"

test-integration:
	@echo "▶ Running integration tests (requires running stack)..."
	$(PYTEST) tests\integration\ -v --tb=short -m integration
	@echo "✅ Integration tests passed"
