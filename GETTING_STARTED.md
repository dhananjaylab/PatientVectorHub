# Getting Started with PatientVectorHub

Choose your development path and follow the guide.

---

## 🚀 Quick Decision Tree

```
Do you want to use Docker locally?
├─ YES → Use Docker (fastest, local-only)
│  └─ See: README.md → "Quick Start: Option 1 - Docker"
│  └─ Windows? → See: WINDOWS_SETUP.md
│
└─ NO → Use Cloud Services (production-like)
   └─ See: CLOUD_QUICKSTART.md (5 min quick start)
   └─ Or: CLOUD_SETUP.md (complete guide)
```

---

## 📋 All Available Guides

### For Docker Setup
1. **Main Entry Point**: [README.md](README.md)
   - Quick start with Docker
   - Service endpoints
   - Test credentials

2. **Windows Users**: [WINDOWS_SETUP.md](WINDOWS_SETUP.md)
   - Docker Desktop setup
   - PowerShell, CMD, Make options
   - Troubleshooting

3. **Windows Deep Dive**: [WINDOWS_IMPLEMENTATION_NOTES.md](WINDOWS_IMPLEMENTATION_NOTES.md)
   - How Windows scripts work
   - Process flow comparison
   - Technical decisions

### For Cloud Setup
1. **Quick Start (5 min)**: [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md)
   - Copy-paste commands
   - Minimal setup
   - Essential environment variables

2. **Complete Guide**: [CLOUD_SETUP.md](CLOUD_SETUP.md)
   - Detailed architecture
   - Setup sequence step-by-step
   - Troubleshooting section
   - Production scaling tips

3. **Cloud Environment Template**: [.env.example.cloud](.env.example.cloud)
   - Annotated examples for AWS, Azure, GCP
   - All cloud service types

### General
1. **Setup Overview**: [SETUP_GUIDE_OVERVIEW.md](SETUP_GUIDE_OVERVIEW.md)
   - Compare Docker vs Cloud
   - When to choose each
   - Support matrix

---

## ⚡ Quick Start

### Option A: Docker (2 minutes)

```bash
git clone https://github.com/your-org/patientvectorhub
cd patientvectorhub
cp .env.example .env
make dev
# Wait for all services to be healthy (~90 seconds)
curl http://localhost:8000/health
```

### Option B: Cloud Services (5 minutes)

```bash
git clone https://github.com/your-org/patientvectorhub
cd patientvectorhub
cp .env.example.cloud .env
# Edit .env with your cloud endpoints

python -m alembic upgrade head
python scripts/seed_data.py
python scripts/setup_weaviate_schema.py
python scripts/setup_qdrant_schema.py
python scripts/create_kafka_topics.py

cd ingestion/embedding-server && python main.py
# In another terminal:
cd api-gateway && uvicorn src.main:app --reload
```

---

## 📚 Documentation Map

```
README.md ⭐ START HERE
├── Option 1: Docker
│   ├── Service Endpoints
│   ├── Test Credentials
│   ├── Developer Workflow
│   │   └── make commands
│   │   └── manual docker commands
│   └── Windows? → WINDOWS_SETUP.md
│
├── Option 2: Cloud Services
│   ├── Configuration
│   ├── Setup Sequence
│   ├── Verification Steps
│   └── Troubleshooting
│
└── Architecture Overview

WINDOWS_SETUP.md (if on Windows + Docker)
├── Prerequisites
├── Setup Instructions
├── Troubleshooting
├── Performance Tips
└── Using Make

CLOUD_QUICKSTART.md (if using Cloud Services)
├── 1. Configure Environment (2 min)
├── 2. Setup Services (2 min)
├── 3. Start Services (1 min)
├── 4. Verify (1 min)
└── Troubleshooting

CLOUD_SETUP.md (detailed Cloud guide)
├── Architecture Overview
├── Prerequisites & Cloud Accounts
├── Configuration (detailed)
├── Setup Sequence (with explanations)
├── Verification (health checks)
├── Development Workflow
├── Common Issues (with solutions)
└── Scaling Up

SETUP_GUIDE_OVERVIEW.md (conceptual)
├── Setup Options comparison
├── Quick Comparison table
├── Choosing Your Setup
├── File Structure
└── Support Matrix

WINDOWS_IMPLEMENTATION_NOTES.md (Windows technical)
├── Process Flow Comparison
├── Feature Parity
├── Architectural Decisions
└── Verification Checklist

.env.example (Docker defaults)
.env.example.cloud (Cloud with examples)
```

---

## ✅ Verification Checklist

After setup, verify everything works:

```bash
# 1. API is responding
curl http://localhost:8000/health

# 2. API is ready (all dependencies healthy)
curl http://localhost:8000/ready

# 3. Database is working
python -m pytest tests/unit -v -k "test_config or test_db"

# 4. Vector stores are responding (cloud only)
curl http://your-weaviate-host:8080/v1/.well-known/ready
curl http://your-qdrant-host:6333/health

# 5. Full test suite
pytest tests/ -v
```

---

## 🆘 Need Help?

1. **Can't find something?** Check [SETUP_GUIDE_OVERVIEW.md](SETUP_GUIDE_OVERVIEW.md)
2. **Docker not working?** See [WINDOWS_SETUP.md](WINDOWS_SETUP.md#troubleshooting)
3. **Cloud setup issues?** See [CLOUD_SETUP.md](CLOUD_SETUP.md#common-issues)
4. **Windows specific?** See [WINDOWS_IMPLEMENTATION_NOTES.md](WINDOWS_IMPLEMENTATION_NOTES.md)

---

## 🎯 What's Included

### Docker Setup (Option 1)
- ✅ All 8 services (Postgres, Redis, Kafka, Weaviate, Qdrant, Vault, Keycloak, Embedding)
- ✅ Automated setup via `make dev`
- ✅ Windows support (Makefile.windows, PowerShell, Batch)
- ✅ Database migrations and seeding
- ✅ Test data (2 tenants, 4 users each, 1000 patients each)

### Cloud Setup (Option 2)
- ✅ Cloud infrastructure configuration
- ✅ Local FastAPI + Embedding server
- ✅ Setup scripts for database, vector stores, Kafka topics
- ✅ Detailed troubleshooting guide
- ✅ Production-ready architecture
- ✅ Cloud-specific examples (AWS, Azure, GCP)

### Both Setups
- ✅ Complete environment configuration
- ✅ LLM API key integration
- ✅ AWS S3 document storage
- ✅ Health checks and verification
- ✅ Comprehensive documentation
- ✅ Windows, macOS, and Linux support

---

## 🗂️ File Organization

```
patientvectorhub/
├── 📄 GETTING_STARTED.md (this file - read first!)
├── 📄 README.md (main setup)
├── 📄 SETUP_GUIDE_OVERVIEW.md (guides overview)
│
├── 🐳 Docker Setup
│   ├── docker-compose.yml
│   ├── Makefile (Linux/macOS)
│   ├── Makefile.windows
│   ├── .env.example
│   ├── WINDOWS_SETUP.md
│   └── WINDOWS_IMPLEMENTATION_NOTES.md
│
├── ☁️ Cloud Setup
│   ├── .env.example.cloud
│   ├── CLOUD_QUICKSTART.md
│   ├── CLOUD_SETUP.md
│   └── scripts/ (setup scripts)
│
├── 🔧 Configuration
│   ├── .env (copy from .env.example or .env.example.cloud)
│   └── api-gateway/src/config.py
│
└── 📦 Services
    ├── api-gateway/ (FastAPI)
    ├── ingestion/ (embedding server + workers)
    ├── vector-store/ (vector store interface)
    ├── rag-engine/ (RAG logic)
    ├── dashboard/ (frontend)
    └── tests/ (unit + integration)
```

---

## 🚀 Next Steps

**Step 1: Choose Your Path**
- Docker? → Read [README.md](README.md)
- Cloud? → Read [CLOUD_QUICKSTART.md](CLOUD_QUICKSTART.md)
- Not sure? → Read [SETUP_GUIDE_OVERVIEW.md](SETUP_GUIDE_OVERVIEW.md)

**Step 2: Follow the Setup**
- Follow step-by-step instructions in your chosen guide
- Configure `.env` or `.env.cloud` with your settings
- Run setup commands

**Step 3: Verify It Works**
```bash
curl http://localhost:8000/health
pytest tests/unit -v
```

**Step 4: Start Developing**
- API docs: http://localhost:8000/docs
- Database: See api-gateway/migrations/
- Tests: See tests/unit/ and tests/integration/

---

## 📞 Quick Reference

### Files to Copy
```bash
cp .env.example .env                    # For Docker
cp .env.example.cloud .env              # For Cloud
```

### Essential Commands
```bash
make dev                                # Start Docker stack
python -m alembic upgrade head         # Migrate database
python scripts/seed_data.py            # Load test data
pytest tests/unit -v                   # Run unit tests
curl http://localhost:8000/health      # Health check
```

### Common Endpoints
```
FastAPI:     http://localhost:8000
API Docs:    http://localhost:8000/docs
Weaviate:    http://localhost:8080 (Docker)
Qdrant:      http://localhost:6333 (Docker)
Keycloak:    http://localhost:8443 (Docker)
Redis:       localhost:6379
Kafka:       localhost:9092
```

---

## 💡 Pro Tips

1. **Start small**: Use `dev-lite` (Docker) to test without Keycloak
2. **Save bandwidth**: Run tests locally, not in cloud
3. **Use envs wisely**: Keep `.env` secrets local, never commit
4. **Monitor logs**: `docker compose logs -f` or `tail` local logs
5. **Test early**: Run `pytest tests/unit` before committing

---

**Ready? Pick your path above and let's go! 🚀**
