# PatientVectorHub

PatientVectorHub is a Windows-friendly, cloud-ready RAG platform for patient document workflows. The repository is organized around four Python services plus a dashboard and shared infrastructure scripts.

## Service Map

| Service | Folder | Purpose | Main dependencies |
| :--- | :--- | :--- | :--- |
| API Gateway | `api-gateway/` | FastAPI entrypoint, health/readiness routes, CORS, auth middleware, Alembic migrations | PostgreSQL, Keycloak, Kafka, Vault |
| Ingestion | `ingestion/` | Document ingestion plumbing, tenant lookup helpers, OpenAI embedding flow, parser/chunker/worker modules | PostgreSQL, Kafka, embedding model, vector stores |
| RAG Engine | `rag-engine/` | Retrieval and LLM orchestration configuration for query flows | Redis, vector store, OpenAI embeddings, LLM providers |
| Vector Store | `vector-store/` | Vector backend abstraction for Weaviate/Qdrant and retrieval storage contracts | Weaviate, Qdrant |

Supporting components:

| Component | Folder/File | Purpose |
| :--- | :--- | :--- |
| Dashboard | `dashboard/` | React/Vite frontend |
| Infrastructure scripts | `scripts/` | Database seeding, vector schema setup, Kafka topic setup, local dev helpers |
| Local infra | `docker-compose.yml`, `infra/` | Local PostgreSQL, Redis, Weaviate, Qdrant, Vault, Kafka, Keycloak |

## Configuration

All services read from the root `.env` file. For cloud development, copy the cloud template and fill in your managed service endpoints:

```powershell
copy .env.example.cloud .env
notepad .env
```

Important cloud settings:

```env
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB?sslmode=require
DATABASE_URL_SYNC=postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DB?sslmode=require
KAFKA_BROKERS=HOST:PORT
KAFKA_SECURITY_PROTOCOL=PLAINTEXT
WEAVIATE_URL=https://YOUR-WEAVIATE-ENDPOINT
WEAVIATE_API_KEY=YOUR_KEY
QDRANT_URL=https://YOUR-QDRANT-ENDPOINT
QDRANT_API_KEY=YOUR_KEY
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL_VERSION=text-embedding-3-large
```

`DATABASE_URL` is used by async application code and Alembic. `DATABASE_URL_SYNC` is used by synchronous scripts such as `scripts\seed_data.py`.

## Prerequisites

- Python 3.9+
- Node.js 18+ for `dashboard/`
- Docker Desktop only if running local infrastructure
- Service-specific cloud credentials if using Aiven/managed services

## Install Dependencies

The repo supports separate virtual environments per service, which is the recommended setup for this project. The local embedding server has its own optional requirements file for future open-source embedding work; it is not needed for the current OpenAI embedding path.

```powershell
python -m venv venv-api-gateway
.\venv-api-gateway\Scripts\activate
pip install --upgrade pip
pip install -r api-gateway\requirements.txt
deactivate

python -m venv venv-ingestion
.\venv-ingestion\Scripts\activate
pip install --upgrade pip
pip install -r ingestion\requirements.txt
deactivate

python -m venv venv-rag-engine
.\venv-rag-engine\Scripts\activate
pip install --upgrade pip
pip install -r rag-engine\requirements.txt
deactivate

python -m venv venv-vector-store
.\venv-vector-store\Scripts\activate
pip install --upgrade pip
pip install -r vector-store\requirements.txt
deactivate
```

## Service Responsibilities And Commands

### API Gateway

Use this service for HTTP API traffic, auth middleware, health checks, and database migrations.

```powershell
.\venv-api-gateway\Scripts\activate
cd api-gateway
python -m alembic upgrade head
uvicorn src.main:app --reload --port 8000
```

Useful endpoints:

```text
http://localhost:8000/health
http://localhost:8000/ready
http://localhost:8000/docs
```

### Ingestion

Use this service area for preparing ingestion data and ingestion infrastructure. The current embedding implementation uses OpenAI; the local open-source embedding server is kept as a future optional path.

Database seed data:

```powershell
.\venv-api-gateway\Scripts\activate
python -u scripts\seed_data.py
```

OpenAI embedding configuration:

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL_VERSION=text-embedding-3-large
OPENAI_API_KEY=YOUR_KEY
```

Vector schemas used by ingestion:

```powershell
.\venv-vector-store\Scripts\activate
python scripts\setup_weaviate_schema.py
python scripts\setup_qdrant_schema.py
```

Kafka topics used by ingestion:

```powershell
.\venv-ingestion\Scripts\activate
python scripts\create_kafka_topics.py
```

### Vector Store

Use this service for Weaviate/Qdrant backend contracts and collection setup. The setup scripts create per-tenant collections for the seeded tenants.

```powershell
.\venv-vector-store\Scripts\activate
python scripts\setup_weaviate_schema.py
python scripts\setup_qdrant_schema.py
```

Created collections:

```text
Weaviate: PatientDocument_00000000_0000_0000_0000_000000000001
Weaviate: PatientDocument_00000000_0000_0000_0000_000000000002
Qdrant:   patient_docs_00000000_0000_0000_0000_000000000001
Qdrant:   patient_docs_00000000_0000_0000_0000_000000000002
```

### RAG Engine

Use this service for retrieval and answer-generation configuration. It reads Redis, vector store, OpenAI embedding settings, and LLM provider settings from root `.env`.

```powershell
.\venv-rag-engine\Scripts\activate
python -c "from src.config import settings; print(settings.VECTOR_BACKEND, settings.EMBEDDING_MODEL_VERSION, settings.LLM_DEFAULT_PROVIDER)"
```

The current repository contains configuration and dependency scaffolding for the RAG engine; runnable API/worker entrypoints can be added as retrieval features are implemented.

## Cloud Initialization Order

For Aiven/cloud-backed development, run these from the repo root unless the command says otherwise:

```powershell
.\venv-api-gateway\Scripts\activate
cd api-gateway
python -m alembic upgrade head
cd ..
python -u scripts\seed_data.py

deactivate
.\venv-vector-store\Scripts\activate
python scripts\setup_weaviate_schema.py
python scripts\setup_qdrant_schema.py

deactivate
.\venv-ingestion\Scripts\activate
python scripts\create_kafka_topics.py
```

Verify PostgreSQL seed data:

```powershell
.\venv-api-gateway\Scripts\activate
python -c "from scripts.seed_data import get_database_url; from sqlalchemy import create_engine, text; e=create_engine(get_database_url(), pool_pre_ping=True); c=e.connect(); print('revision', c.execute(text('select version_num from alembic_version')).scalar()); print('tenants', c.execute(text('select count(*) from tenants')).scalar()); print('users', c.execute(text('select count(*) from users')).scalar()); print('patients', c.execute(text('select count(*) from patients')).scalar()); c.close()"
```

Expected seeded PostgreSQL counts:

```text
revision 002
tenants 2
users 8
patients 2000
```

Aiven's table browser may show only the first 100 rows. Use `SELECT COUNT(*) FROM patients;` in the Aiven query editor to verify the full count.

## Local Docker Development

If you want to run local infrastructure instead of cloud services, start Docker Desktop and use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev
```

For a lighter local stack:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev-lite
```

Common tasks:

| Task | PowerShell command |
| :--- | :--- |
| Start full local stack | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev` |
| Start lite local stack | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task dev-lite` |
| Stop stack | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task stop` |
| Run migrations | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task migrate` |
| Seed PostgreSQL | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task seed` |
| Setup vector stores | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task setup-vector-stores` |
| Create Kafka topics | `powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Task kafka-topics` |

## Dashboard

```powershell
cd dashboard
npm install
npm run dev
```

Default dashboard URL:

```text
http://localhost:5173
```

## Test Credentials

Synthetic users created by `scripts\seed_data.py`:

| Email | Role | Tenant |
| :--- | :--- | :--- |
| `admin@tenant1.test` | Admin | Acme Health |
| `engineer@tenant1.test` | Engineer | Acme Health |
| `analyst@tenant1.test` | Analyst | Acme Health |
| `auditor@tenant1.test` | Auditor | Acme Health |
| `admin@tenant2.test` | Admin | Riverside Medical |
| `engineer@tenant2.test` | Engineer | Riverside Medical |
| `analyst@tenant2.test` | Analyst | Riverside Medical |
| `auditor@tenant2.test` | Auditor | Riverside Medical |

All synthetic test users share the Keycloak password:

```text
test-password-123
```

## Troubleshooting

### PostgreSQL Still Tries `localhost:5432`

Check that root `.env` contains cloud database URLs and that you launched the script from this repo:

```powershell
Get-Content .env | Select-String "DATABASE_URL"
```

Then rerun:

```powershell
.\venv-api-gateway\Scripts\activate
python -u scripts\seed_data.py
```

### Aiven Shows Only 100 Patients

That is a UI preview limit. Run:

```sql
SELECT COUNT(*) FROM patients;
```

### Kafka Cloud Authentication

`KAFKA_BROKERS` and optional `KAFKA_SECURITY_PROTOCOL`, `KAFKA_USERNAME`, `KAFKA_PASSWORD`, `KAFKA_SASL_MECHANISM`, `KAFKA_SSL_CAFILE`, `KAFKA_SSL_CERTFILE`, and `KAFKA_SSL_KEYFILE` are loaded from `.env`. Aiven Kafka usually requires SSL/SASL or service certificates; copy those values from the Aiven console before running `scripts\create_kafka_topics.py`.

### Vector Store Cloud Authentication

For Weaviate Cloud, set both `WEAVIATE_URL` and `WEAVIATE_API_KEY`. For Qdrant Cloud, set both `QDRANT_URL` and `QDRANT_API_KEY`. If these are empty, setup scripts fall back to host/port values.

### Windows Console Encoding

Use unbuffered output for long setup scripts:

```powershell
python -u scripts\seed_data.py
```

### Docker Not Found

Docker commands require Docker Desktop on PATH. Cloud-only development does not require Docker for PostgreSQL, Weaviate, Qdrant, or Kafka if those services are managed externally.