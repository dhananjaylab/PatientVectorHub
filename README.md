# PatientVectorHub

Enterprise-scale HIPAA-compliant RAG platform for 1.5B patient documents.

## Quick Start (Phase 1)

```bash
# 1. Clone and configure
git clone https://github.com/your-org/patientvectorhub
cd patientvectorhub
cp .env.example .env
# Edit .env — add your LLM API keys

# 2. Start local stack
make dev          # All 8 services + migrate + seed + setup

# 3. Verify
curl http://localhost:8000/health    # {"status": "alive"}
curl http://localhost:8000/ready     # {"status": "ready", "checks": {...}}

# 4. Run unit tests
make test-unit

# 5. Run integration tests (stack must be running)
make test-integration
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

```bash
make help           # All available commands
make dev            # Start full stack
make dev-lite       # Start minimal stack (no Keycloak/Qdrant/Embedding)
make test-unit      # Fast unit tests (no stack needed)
make test-rls       # HIPAA gate: tenant isolation must return 0 rows
make lint           # ruff + mypy + eslint
make format         # Auto-format all code
make logs           # Tail container logs
make clean          # Remove all containers + volumes
```

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
