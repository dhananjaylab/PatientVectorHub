# Cloud-Based Development Setup

This guide helps you run PatientVectorHub using cloud instances for infrastructure (Kafka, PostgreSQL, Redis, Weaviate, Qdrant) while running local services (FastAPI, embedding server, etc.).

---

## Architecture Overview

### Local Services (Your Machine)
- FastAPI API Gateway (port 8000)
- Embedding Model Server (port 8001)
- Dashboard (port 5173, optional)
- Local Python workers/scripts

### Cloud Services
- PostgreSQL (managed database)
- Redis (managed cache)
- Apache Kafka (managed streaming)
- Weaviate (managed vector store)
- Qdrant (managed vector store - DR)
- Vault (managed secrets)
- Keycloak (managed auth)

---

## Prerequisites

### 1. Cloud Accounts & Instances

**PostgreSQL** (managed, e.g., AWS RDS, Azure Database, GCP Cloud SQL)
- Create a database user: `pvh`
- Create a database: `pvh`
- Note the connection string:
  ```
  postgresql://pvh:PASSWORD@host:5432/pvh
  ```

**Redis** (managed, e.g., AWS ElastiCache, Azure Cache, GCP Memorystore)
- Note the endpoint and port
- Connection URL:
  ```
  redis://host:port/0
  ```

**Kafka** (managed, e.g., AWS MSK, Confluent Cloud, Aiven)
- Note the bootstrap servers
- Connection string:
  ```
  host1:port,host2:port,host3:port
  ```

**Weaviate** (self-hosted on EC2/VM or managed via Weaviate Cloud)
- Note the host and gRPC port
- Connection URLs:
  ```
  WEAVIATE_HOST=host
  WEAVIATE_PORT=8080
  WEAVIATE_GRPC_PORT=50051
  ```

**Qdrant** (self-hosted on EC2/VM or managed via Qdrant Cloud)
- Note the host and port
- Connection URLs:
  ```
  QDRANT_HOST=host
  QDRANT_PORT=6333
  ```

**Vault** (optional, managed or self-hosted)
- For dev, you can skip this and use `.env` directly

**Keycloak** (optional, managed or self-hosted)
- For dev, you can mock this or use a local instance

### 2. Local Prerequisites

```bash
# Python 3.9+
python --version

# pip dependencies
pip install -r api-gateway/requirements.txt
pip install -r ingestion/requirements.txt
pip install -r rag-engine/requirements.txt
pip install -r vector-store/requirements.txt

# Node.js (for dashboard, optional)
npm install -D
cd dashboard && npm install && cd ..
```

---

## Configuration

### 1. Update `.env` with Cloud Endpoints

```env
# ── Database ─────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://pvh:YOUR_PASSWORD@your-db-host:5432/pvh
DATABASE_URL_SYNC=postgresql+psycopg2://pvh:YOUR_PASSWORD@your-db-host:5432/pvh

# ── Cache & Messaging ─────────────────────────────────────────────────────────
REDIS_URL=redis://your-redis-host:6379/0
KAFKA_BROKERS=kafka1.your-domain:9092,kafka2.your-domain:9092,kafka3.your-domain:9092

# ── Vector Stores ─────────────────────────────────────────────────────────────
VECTOR_BACKEND=weaviate
WEAVIATE_HOST=your-weaviate-host
WEAVIATE_PORT=8080
WEAVIATE_GRPC_PORT=50051
QDRANT_HOST=your-qdrant-host
QDRANT_PORT=6333

# ── Embedding Model ───────────────────────────────────────────────────────────
EMBEDDING_MODEL_URL=http://localhost:8001
EMBEDDING_MODEL_VERSION=clinical-bert-v2.1

# ── Vault ─────────────────────────────────────────────────────────────────────
VAULT_ADDR=http://your-vault-host:8200
VAULT_TOKEN=dev-root-token

# ── Keycloak ──────────────────────────────────────────────────────────────────
KEYCLOAK_BASE_URL=http://your-keycloak-host:8443
KEYCLOAK_REALM=patientvectorhub
KEYCLOAK_JWKS_URL=http://your-keycloak-host:8443/realms/patientvectorhub/protocol/openid-connect/certs
KEYCLOAK_ISSUER=http://your-keycloak-host:8443/realms/patientvectorhub
KEYCLOAK_CLIENT_ID=pvh-spa

# ── LLM Providers (REQUIRED) ──────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIza...
LLM_DEFAULT_PROVIDER=anthropic
LLM_MAX_TOKENS=1000

# ── AWS (for S3) ──────────────────────────────────────────────────────
AWS_REGION=us-east-1
S3_DOCUMENT_BUCKET=pvh-documents-dev
S3_BACKUP_BUCKET=pvh-backups-dev

# ── Observability ─────────────────────────────────────────────────────
JAEGER_ENDPOINT=http://your-jaeger-host:4317
LOG_LEVEL=DEBUG
ENVIRONMENT=development

# ── App ───────────────────────────────────────────────────────────────
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

### 2. Verify Connectivity

```bash
# Test PostgreSQL
psql "postgresql://pvh:PASSWORD@host:5432/pvh" -c "SELECT version();"

# Test Redis
redis-cli -h your-redis-host -p 6379 ping

# Test Kafka
python -c "from kafka import KafkaProducer; producer = KafkaProducer(bootstrap_servers=['host:port']); print('OK')"

# Test Weaviate
curl -X GET "http://your-weaviate-host:8080/v1/.well-known/ready"

# Test Qdrant
curl -X GET "http://your-qdrant-host:6333/health"
```

---

## Setup Sequence

### 1. Initialize Database

```bash
# Apply migrations
cd api-gateway
python -m alembic upgrade head
cd ..

# Output should show:
# INFO  [alembic.runtime.migration] Context impl PostgreSqlImpl.
# INFO  [alembic.runtime.migration] Will assume transactional DDL is supported by the target database
# INFO  [alembic.runtime.migration] Running upgrade head
```

### 2. Seed Test Data

```bash
python scripts/seed_data.py

# Output: Creates 2 tenants, 4 users per tenant, 1000 patients each
```

### 3. Setup Vector Stores

```bash
# Weaviate
python scripts/setup_weaviate_schema.py

# Qdrant
python scripts/setup_qdrant_schema.py
```

### 4. Create Kafka Topics

```bash
python scripts/create_kafka_topics.py
```

### 5. Initialize Vault (if using)

```bash
bash scripts/vault_init.sh
```

### 6. Start Embedding Server

```bash
cd ingestion/embedding-server
pip install -r requirements.txt
python main.py

# Runs on http://localhost:8001
```

### 7. Start FastAPI

```bash
cd api-gateway
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

---

## Verification

### Health Checks

```bash
# FastAPI
curl http://localhost:8000/health
# Expected: {"status": "alive", "timestamp": "..."}

# API Ready Check (includes all dependencies)
curl http://localhost:8000/ready
# Expected: {"status": "ready", "checks": {"database": "healthy", ...}}

# Weaviate
curl -X GET "http://your-weaviate-host:8080/v1/.well-known/ready"
# Expected: {"status":"ready"}

# Qdrant
curl -X GET "http://your-qdrant-host:6333/health"
# Expected: {"status":"ok"}

# Redis
redis-cli -h your-redis-host ping
# Expected: PONG

# Kafka
python -c "
from kafka.admin import KafkaAdminClient
admin = KafkaAdminClient(bootstrap_servers=['host:port'])
topics = admin.list_topics()
print('Topics:', list(topics.keys()))
"
```

### Test Data Verification

```bash
# Check if users were created
python -c "
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

engine = create_engine('postgresql://pvh:PASSWORD@host:5432/pvh')
Session = sessionmaker(bind=engine)
session = Session()

from api_gateway.src.models import User
users = session.query(User).all()
print(f'Users created: {len(users)}')
"
```

---

## Development Workflow

### Running Unit Tests

```bash
# No external dependencies
pytest tests/unit -v --tb=short
```

### Running Integration Tests

```bash
# Requires all cloud services running
pytest tests/integration -v --tb=short -m integration
```

### Running All Tests

```bash
pytest tests/ -x --cov=src --cov-fail-under=60 --cov-report=term-missing -q
```

### Debugging

```bash
# Tail logs from embedding server
# (in its terminal or via logging)

# Check API logs
# FastAPI logs to console in development mode

# Database queries (if you enabled query logging in .env)
# LOG_LEVEL=DEBUG in .env

# Kafka topic messages
python -c "
from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    'document-ingest',
    bootstrap_servers=['host:port'],
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

for message in consumer:
    print(message.value)
"
```

---

## Common Issues

### PostgreSQL Connection Refused
```bash
# Check if database is accessible
telnet your-db-host 5432

# Verify credentials
psql "postgresql://pvh:PASSWORD@your-db-host:5432/pvh" -c "SELECT 1;"

# Check firewall/security groups allow inbound on port 5432
```

### Redis Connection Timeout
```bash
# Test Redis connectivity
redis-cli -h your-redis-host -p 6379 ping

# Check if AUTH is required
redis-cli -h your-redis-host -p 6379 -a YOUR_PASSWORD ping
```

### Kafka Broker Connection Failed
```bash
# Verify bootstrap servers
python -c "
from kafka import KafkaProducer
producer = KafkaProducer(bootstrap_servers=['host:port'])
print('Connected OK')
"

# Check SASL/SSL if required
# Update KAFKA_BROKERS in .env with proper format
```

### Weaviate Schema Creation Failed
```bash
# Check Weaviate connectivity
curl -X GET "http://your-weaviate-host:8080/v1/schema"

# Re-run setup with verbose output
python scripts/setup_weaviate_schema.py
```

### Qdrant Schema Creation Failed
```bash
# Check Qdrant connectivity
curl -X GET "http://your-qdrant-host:6333/health"

# Check if collections exist
curl -X GET "http://your-qdrant-host:6333/collections"
```

---

## Scaling Up

### From Development to Testing

1. Upgrade cloud instances to larger sizes
2. Enable backups on all databases
3. Setup monitoring (CloudWatch, Datadog, etc.)
4. Enable SSL/TLS for all connections
5. Update `.env` with monitoring endpoints

### From Testing to Production

1. Use managed services (RDS, ElastiCache, MSK, etc.)
2. Enable encryption at rest and in transit
3. Setup VPCs, security groups, network policies
4. Use Vault for secrets management
5. Enable audit logging
6. Setup automated backups and disaster recovery

---

## Next Steps

1. ✅ Configure `.env` with cloud endpoints
2. ✅ Verify connectivity to all cloud services
3. ✅ Run setup scripts (migrate, seed, create topics)
4. ✅ Start embedding server
5. ✅ Start FastAPI
6. ✅ Run health checks
7. ✅ Run integration tests
8. 🚀 Begin development!

---

## Quick Reference

### Essential Commands

```bash
# Setup
python -m alembic upgrade head          # Migrate database
python scripts/seed_data.py             # Seed test data
python scripts/setup_weaviate_schema.py # Setup Weaviate
python scripts/setup_qdrant_schema.py   # Setup Qdrant
python scripts/create_kafka_topics.py   # Create Kafka topics

# Run
cd ingestion/embedding-server && python main.py  # Start embeddings (port 8001)
cd api-gateway && uvicorn src.main:app --reload  # Start API (port 8000)

# Test
pytest tests/unit -v                    # Unit tests
pytest tests/integration -v -m integration  # Integration tests
curl http://localhost:8000/health      # Health check
```

### Environment Variables Needed

- `DATABASE_URL` - PostgreSQL async connection
- `DATABASE_URL_SYNC` - PostgreSQL sync connection
- `REDIS_URL` - Redis connection
- `KAFKA_BROKERS` - Kafka bootstrap servers
- `WEAVIATE_HOST`, `WEAVIATE_PORT`, `WEAVIATE_GRPC_PORT`
- `QDRANT_HOST`, `QDRANT_PORT`
- `EMBEDDING_MODEL_URL` - Point to localhost:8001
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` or `GEMINI_API_KEY`
- `AWS_REGION`, `S3_DOCUMENT_BUCKET`, `S3_BACKUP_BUCKET` (for document storage)

---

## Support

If you encounter issues:

1. Check `.env` for correct endpoints
2. Verify cloud service connectivity with `telnet` or cloud provider CLI
3. Check logs: `LOG_LEVEL=DEBUG` in `.env`
4. Review cloud service documentation for connection details
5. Ensure firewall/security groups allow inbound traffic on required ports
