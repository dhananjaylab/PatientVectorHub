# PatientVectorHub

Enterprise-scale HIPAA-compliant RAG platform for 1.5B patient documents.

## Quick Start (Phase 1)

### Option 1: Docker (Local Development)

```bash
# 1. Clone and configure
git clone https://github.com/your-org/patientvectorhub
cd patientvectorhub
cp .env.example .env
# Edit .env — add your LLM API keys

# 2. Start local stack (all 8 services via Docker)
make dev          # All 8 services + migrate + seed + setup

# 3. Verify
curl http://localhost:8000/health    # {"status": "alive"}
curl http://localhost:8000/ready     # {"status": "ready", "checks": {...}}

# 4. Run unit tests
make test-unit

# 5. Run integration tests (stack must be running)
make test-integration
```

### Option 2: Cloud Services (Production-Ready Development)

Use managed cloud services for PostgreSQL, Redis, Kafka, Weaviate, and Qdrant:

**Quick Start (5 min):** See [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md)

**Full Guide:** See [CLOUD_SETUP.md](CLOUD_SETUP.md)

```bash
# 1. Configure cloud endpoints
cp .env.example.cloud .env
# Edit with your cloud endpoints

# 2. Initialize services
python -m alembic upgrade head
python scripts/seed_data.py
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py
python scripts/create_kafka_topics.py

# 3. Start local services
cd ingestion/embedding-server && python main.py   # Terminal 1: Embeddings (port 8001)
cd api-gateway && uvicorn src.main:app --reload   # Terminal 2: API (port 8000)

# 4. Verify
curl http://localhost:8000/health
```

## Service Endpoints (local)

| Service        | URL                           |
|----------------|-------------------------------|
| FastAPI        | http://localhost:8000         |
| API Docs       | http://localhost:8000/docs    |
| Keycloak       | http://localhost:8443         |
| Weaviate       | http://localhost:8080         |
| Qdrant         | http://localhost:6333         |
| Vault          | http://localhost:8200         |
| Kafka          | localhost:9092                |
| Embedding      | http://localhost:8001         |
| Dashboard      | http://localhost:5173         |

## Test Credentials

All users have password: `test-password-123`

| Email                    | Role     | Tenant |
|--------------------------|----------|--------|
| admin@tenant1.test       | admin    | Acme Health |
| engineer@tenant1.test    | engineer | Acme Health |
| analyst@tenant1.test     | analyst  | Acme Health |
| auditor@tenant1.test     | auditor  | Acme Health |
| admin@tenant2.test       | admin    | Riverside Medical |
| engineer@tenant2.test    | engineer | Riverside Medical |

## Implementation Phases

| Phase | Scope                       | Status     |
|-------|-----------------------------|------------|
| 1     | Environment Setup           | ✅ Complete |
| 2     | Database + RLS              | 🔜 Next    |
| 3     | Auth + RBAC                 | ⬜ Pending |
| 4     | Ingestion Pipeline          | ⬜ Pending |
| 5     | Embedding Model Server      | ⬜ Pending |
| 6     | Vector Store Layer          | ⬜ Pending |
| 7     | RAG Query Engine            | ⬜ Pending |
| 8     | REST API + Kong             | ⬜ Pending |
| 9     | Frontend Dashboard          | ⬜ Pending |
| 10    | Observability + Security    | ⬜ Pending |
| 11    | Testing + Load Tests        | ⬜ Pending |
| 12    | Production Deployment       | ⬜ Pending |

## Developer Workflow

### Quick Commands

| Task | Docker | Cloud |
|------|--------|-------|
| Start all services | `make dev` | See [CLOUD_SETUP.md](CLOUD_SETUP.md) |
| Start minimal stack | `make dev-lite` | Manual setup in [CLOUD_SETUP.md](CLOUD_SETUP.md) |
| Run tests | `make test-unit` | `pytest tests/unit -v` |
| View logs | `make logs` | Check service terminals/CloudWatch |
| Stop services | `make stop` | Ctrl+C in each terminal |
| Clean volumes | `make clean` | N/A (cloud-managed) |

### Using Make (Docker - Recommended for Local Dev)

```bash
make help           # All available commands
make dev            # Start full stack (all 8 services)
make dev-lite       # Start minimal stack (Postgres, Redis, Weaviate, Kafka, Vault)
make test-unit      # Fast unit tests (no stack needed)
make test-rls       # HIPAA gate: tenant isolation must return 0 rows
make lint           # ruff + mypy + eslint
make format         # Auto-format all code
make logs           # Tail container logs
make clean          # Remove all containers + volumes
```

### Cloud Services (Production-Ready Development)

**Setup sequence:**

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env with cloud endpoints (PostgreSQL, Redis, Kafka, Weaviate, Qdrant)

# 2. Initialize infrastructure
python -m alembic upgrade head
python scripts/seed_data.py
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py
python scripts/create_kafka_topics.py

# 3. Start local services (in separate terminals)
cd ingestion/embedding-server && python main.py
cd api-gateway && uvicorn src.main:app --reload

# 4. Verify
curl http://localhost:8000/health
pytest tests/integration -v
```

**See [CLOUD_SETUP.md](CLOUD_SETUP.md) for complete cloud development guide.**

### Manual Commands (Development Phase - Docker)

**All 8 Services + Setup**

```bash
# 1. Start all 8 containers
docker compose up -d

# 2. Wait for services to be healthy (check logs if needed)
docker compose logs -f --tail=50

# 3. Once healthy, run migrations
cd api-gateway
python -m alembic upgrade head
cd ..

# 4. Initialize Vault with dev secrets
bash scripts/vault_init.sh

# 5. Create Kafka topics
python scripts/create_kafka_topics.py

# 6. Setup vector store schemas
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py

# 7. Seed synthetic test data
python scripts/seed_data.py

# 8. Verify all services
curl http://localhost:8000/health        # FastAPI
curl http://localhost:8080/v1/.well-known/ready  # Weaviate
curl http://localhost:6333/health        # Qdrant
curl http://localhost:8200/v1/sys/health # Vault (requires token)
```

**Service-Specific Commands**

```bash
# View container logs
docker compose logs -f postgres           # Database
docker compose logs -f redis              # Cache
docker compose logs -f kafka              # Message queue
docker compose logs -f weaviate           # Vector store (primary)
docker compose logs -f qdrant             # Vector store (DR)
docker compose logs -f vault              # Secrets
docker compose logs -f keycloak           # Auth
docker compose logs -f embedding-server   # Embeddings

# Stop all services
docker compose down

# Stop and remove volumes (reset state)
docker compose down -v

# Run just migrations
cd api-gateway && python -m alembic upgrade head && cd ..

# Run just seeding
python scripts/seed_data.py

# Run just vector store setup
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py

# Run just Kafka topics
python scripts/create_kafka_topics.py
```

**Windows Users**

```powershell
# PowerShell (recommended)
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev

# Or use batch file
scripts\dev.bat dev

# Or use make (if installed)
make -f Makefile.windows dev
```

See [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for full Windows documentation.

## Architecture

All-OSS stack — no paid managed services:

- **API Gateway**: FastAPI + Kong OSS
- **Auth**: Keycloak 24 (OIDC PKCE)
- **Secrets**: HashiCorp Vault OSS
- **Messaging**: Apache Kafka via Strimzi
- **Database**: CloudNativePG (PostgreSQL 15)
- **Vector (primary)**: Weaviate
- **Vector (DR)**: Qdrant
- **Embeddings**: Self-hosted clinical-bert (emilyalsentzer/Bio_ClinicalBERT)
- **LLMs**: Anthropic Claude + OpenAI GPT-4o + Google Gemini
- **Observability**: Prometheus + Grafana + Jaeger + Loki
