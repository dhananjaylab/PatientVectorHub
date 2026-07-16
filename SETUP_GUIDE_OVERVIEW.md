# PatientVectorHub Setup Guide Overview

This document helps you choose the right setup path for your development phase.

---

## Setup Options

### 🐳 Option 1: Docker (Easiest for Local Development)

**Best for:** Quick local development, testing, learning the system

**Files:**
- `Makefile` (original Linux/macOS)
- `Makefile.windows` (Windows)
- `docker-compose.yml` (all 8 services)
- `.env.example` (default endpoints)

**Quick Start:**
```bash
make dev  # or make -f Makefile.windows dev (Windows)
```

**Documentation:**
- [README.md](README.md) - Main setup instructions
- [WINDOWS_SETUP.md](WINDOWS_SETUP.md) - Windows-specific guide
- [WINDOWS_IMPLEMENTATION_NOTES.md](WINDOWS_IMPLEMENTATION_NOTES.md) - Technical details

**Services included:**
✓ PostgreSQL ✓ Redis ✓ Kafka ✓ Weaviate ✓ Qdrant ✓ Vault ✓ Keycloak ✓ Embedding Server

---

### ☁️ Option 2: Cloud Services (Production-Ready Development)

**Best for:** Production-like environment, cloud infrastructure testing, team collaboration

**Cloud services used:**
- PostgreSQL (AWS RDS, Azure Database, GCP Cloud SQL)
- Redis (AWS ElastiCache, Azure Cache, GCP Memorystore)
- Kafka (AWS MSK, Confluent Cloud, Aiven)
- Weaviate (EC2/self-hosted or Weaviate Cloud)
- Qdrant (EC2/self-hosted or Qdrant Cloud)
- Vault (optional, self-hosted or AWS Secrets Manager)
- Keycloak (optional, self-hosted)

**Local services:**
- FastAPI API Gateway (port 8000)
- Embedding Model Server (port 8001)
- Your code and scripts

**Files:**
- `.env.example.cloud` (cloud endpoint template)
- Setup scripts (`seed_data.py`, `setup_weaviate_schema.py`, etc.)
- Manual setup commands (no Docker Compose)

**Quick Start (5 min):**
```bash
cp .env.example.cloud .env
# Edit with cloud endpoints
python -m alembic upgrade head
python scripts/seed_data.py
cd ingestion/embedding-server && python main.py  # Terminal 1
cd api-gateway && uvicorn src.main:app --reload  # Terminal 2
```

**Documentation:**
- [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md) - 5-minute quick start
- [CLOUD_SETUP.md](CLOUD_SETUP.md) - Complete guide with troubleshooting

---

## Quick Comparison

| Aspect | Docker | Cloud |
|--------|--------|-------|
| **Setup Time** | 5 min | 10-15 min |
| **Local Overhead** | 4-8GB RAM, 30GB disk | ~500MB for Python |
| **Cost** | $0 (local only) | $$ (cloud services) |
| **Production Readiness** | Development only | Production-ready |
| **Scalability** | Single machine | Unlimited |
| **Collaboration** | Local only | Team-wide |
| **Monitoring** | docker logs | CloudWatch/cloud provider |
| **Backup/DR** | Manual | Cloud provider managed |
| **Security** | localhost only | SSL/TLS, VPC isolation |
| **Complexity** | Low | Medium |

---

## Choosing Your Setup

### Choose Docker If:
- ✓ You want the quickest local setup
- ✓ You're learning/exploring the system
- ✓ You have limited cloud budget
- ✓ You're on a machine with good specs (8GB+ RAM)
- ✓ You prefer running everything locally

### Choose Cloud If:
- ✓ You want production-like environment
- ✓ Your team needs to collaborate
- ✓ You're testing with real cloud infrastructure
- ✓ You want persistent data
- ✓ You need monitoring/observability
- ✓ You're preparing for production deployment

---

## File Structure

```
PatientVectorHub/
├── README.md                          # Main entry point
├── SETUP_GUIDE_OVERVIEW.md            # This file
│
├── docker-compose.yml                 # Docker configuration
├── Makefile                           # Linux/macOS setup
├── Makefile.windows                   # Windows setup
├── WINDOWS_SETUP.md                   # Windows guide
├── WINDOWS_IMPLEMENTATION_NOTES.md    # Windows technical details
│
├── .env.example                       # Docker environment template
├── .env.example.cloud                 # Cloud environment template
├── CLOUD_QUICKSTART.md                # 5-minute cloud setup
├── CLOUD_SETUP.md                     # Complete cloud guide
│
├── scripts/
│   ├── dev.ps1                        # PowerShell setup script
│   ├── dev.bat                        # Batch setup script
│   ├── seed_data.py                   # Load test data
│   ├── create_kafka_topics.py         # Setup Kafka
│   ├── setup_weaviate_schema.py       # Setup Weaviate
│   ├── setup_qdrant_schema.py         # Setup Qdrant
│   └── vault_init.sh                  # Initialize Vault
│
├── api-gateway/
│   ├── src/config.py                  # Configuration loader
│   └── migrations/                    # Database migrations
│
├── ingestion/
│   ├── embedding-server/              # Local embedding server
│   └── src/                           # Ingestion pipeline
│
└── tests/
    ├── unit/                          # Unit tests (no dependencies)
    └── integration/                   # Integration tests (requires services)
```

---

## Getting Help

### Before Reaching Out

1. **Docker Issues:**
   - Check [WINDOWS_SETUP.md](WINDOWS_SETUP.md) for Windows-specific problems
   - Run `docker compose logs [service]` to view service logs
   - Ensure all ports are available (`docker ps`)

2. **Cloud Issues:**
   - Verify endpoints in `.env` are correct
   - Check cloud provider firewall/security groups allow inbound traffic
   - See [CLOUD_SETUP.md](CLOUD_SETUP.md#common-issues) for troubleshooting

3. **General Issues:**
   - Ensure Python 3.9+ is installed
   - Verify API keys are valid (Anthropic, OpenAI, etc.)
   - Check `.env` file is not committed to git

### Common Commands

```bash
# Health checks
curl http://localhost:8000/health          # FastAPI
curl http://localhost:8000/ready           # Full stack
pytest tests/unit -v                       # Unit tests

# Logs
docker compose logs -f [service]           # Docker: service logs
tail -f ~/.venv/lib/python*/site-packages/api_gateway.log  # Cloud: API logs

# Cleanup
make clean                                 # Docker: stop and remove volumes
# Cloud: manual cleanup (no docker)

# Configuration
cat .env | grep DATABASE_URL               # Check current config
```

---

## Next Steps

1. **Choose your setup** (Docker or Cloud)
2. **Follow the appropriate guide:**
   - Docker: Start with [README.md](README.md)
   - Cloud: Start with [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md)
3. **Verify everything works:**
   - `curl http://localhost:8000/health`
   - `pytest tests/unit -v`
4. **Start developing:**
   - API docs: http://localhost:8000/docs
   - Run integration tests: `pytest tests/integration -v`

---

## Support Matrix

| Issue | Docker | Cloud | Solution |
|-------|--------|-------|----------|
| Can't connect to service | Check docker compose logs | Check endpoint + firewall | See setup guide |
| Database migrations fail | Check Postgres is healthy | Check cloud DB endpoint | `python -m alembic upgrade head` |
| API won't start | Check port 8000 is free | Check dependencies installed | `pip install -r requirements.txt` |
| Tests fail | Run `make dev` first | Run setup scripts first | See CLOUD_SETUP.md |
| Windows issues | See WINDOWS_SETUP.md | Python should work on Windows | Use PowerShell or WSL |

---

## Document Index

### Setup Guides
- **Quick Start**: [README.md](README.md)
- **Docker**: [README.md](README.md) + manual commands section
- **Windows Docker**: [WINDOWS_SETUP.md](WINDOWS_SETUP.md)
- **Cloud (Quick)**: [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md)
- **Cloud (Full)**: [CLOUD_SETUP.md](CLOUD_SETUP.md)

### Technical Documentation
- **Windows Implementation**: [WINDOWS_IMPLEMENTATION_NOTES.md](WINDOWS_IMPLEMENTATION_NOTES.md)
- **Configuration**: `.env.example` and `.env.example.cloud`

### Automation
- **Linux/macOS**: `Makefile`
- **Windows**: `Makefile.windows`, `scripts/dev.ps1`, `scripts/dev.bat`

---

## File Sizes for Reference

```
Docker approach:
- Docker images: ~3-5GB (downloaded once)
- Running containers: 4-8GB RAM
- Volumes: ~30GB disk

Cloud approach:
- Local Python: ~500MB
- Cloud services: Billable (varies by provider)
```

---

## Version Information

- **PatientVectorHub Phase**: 1 (Environment Setup ✅ Complete)
- **Docker Compose**: v2.0+
- **Python**: 3.9+
- **Node.js**: 18+ (optional, for dashboard)

---

**Ready to start? Choose your path above and follow the guide!**
