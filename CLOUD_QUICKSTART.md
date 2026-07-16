# Cloud Development - Quick Start (5 minutes)

For experienced developers who want to skip the lengthy docs and get started with cloud services immediately.

---

## Prerequisites

- Python 3.9+
- pip, git
- Cloud service endpoints (PostgreSQL, Redis, Kafka, Weaviate, Qdrant)
- LLM API key (Anthropic, OpenAI, or Google)

---

## 1. Configure Environment (2 min)

```bash
cp .env.example.cloud .env

# Edit .env with your cloud endpoints:
# - DATABASE_URL (PostgreSQL)
# - REDIS_URL (Redis)
# - KAFKA_BROKERS (Kafka)
# - WEAVIATE_HOST, WEAVIATE_PORT, WEAVIATE_GRPC_PORT
# - QDRANT_HOST, QDRANT_PORT
# - LLM API keys (ANTHROPIC_API_KEY, etc.)
# - Cloudflare R2 credentials and endpoint url if using R2
```

---

## 2. Setup Services (2 min)

```bash
# Install dependencies
pip install -r api-gateway/requirements.txt
pip install -r ingestion/requirements.txt

# Verify connectivity (optional but recommended)
python -c "from sqlalchemy import create_engine; engine = create_engine(os.getenv('DATABASE_URL')); print(engine.execute('SELECT 1;'))"

# Initialize database
cd api-gateway
python -m alembic upgrade head
cd ..

# Seed test data
python scripts/seed_data.py

# Setup vector stores
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py

# Create Kafka topics
python scripts/create_kafka_topics.py
```

---

## 3. Start Services (1 min)

**Terminal 1 - Embedding Server:**
```bash
cd ingestion/embedding-server
pip install -r requirements.txt
python main.py
# Runs on http://localhost:8001
```

**Terminal 2 - FastAPI:**
```bash
cd api-gateway
uvicorn src.main:app --reload --port 8000
# Runs on http://localhost:8000
```

---

## 4. Verify (1 min)

```bash
# Health check
curl http://localhost:8000/health

# API docs
open http://localhost:8000/docs

# Run tests
pytest tests/unit -v
pytest tests/integration -v
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Connection refused` | Check cloud endpoint in `.env`, verify firewall allows inbound |
| `Authentication failed` | Check credentials (password, token, API key) in `.env` |
| `Timeout connecting to PostgreSQL` | Increase `connect_timeout` in `DATABASE_URL` |
| `Redis MOVED error` | If using Redis cluster, ensure Redis client supports cluster |
| `Weaviate schema error` | Run `python scripts/setup_weaviate_schema.py` again |
| `Kafka topic error` | Run `python scripts/create_kafka_topics.py` again |
| `LLM API rate limit` | Check API key is correct, not multiple keys in use |

---

## Next Steps

- Read [CLOUD_SETUP.md](CLOUD_SETUP.md) for detailed documentation
- Run integration tests: `pytest tests/integration -v`
- Check API docs: http://localhost:8000/docs
- Start developing!

---

## Essential Environment Variables

```env
# Minimum required
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0
KAFKA_BROKERS=host1:9092,host2:9092,host3:9092
WEAVIATE_HOST=host
WEAVIATE_PORT=8080
QDRANT_HOST=host
QDRANT_PORT=6333
ANTHROPIC_API_KEY=sk-ant-...
```

That's it! You're ready to develop.
