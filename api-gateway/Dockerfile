# api-gateway/Dockerfile
#
# Phase 7 change: build context moved from ./api-gateway to the REPO ROOT,
# same change ingestion/Dockerfile got in Phase 4 and for the same reason —
# routers/query.py does `from rag_engine.retriever import retrieve` and
# `from rag_engine.synthesizer import RAGSynthesizer` (which themselves
# import `from vector_store.interface import ...`), so this image needs
# rag-engine/src/ AND vector-store/src/ copied in alongside api-gateway/src/,
# under the module names those imports expect. Docker Compose does not
# currently run api-gateway as a service (it's local-uvicorn-only per the
# README's venv workflow) — this Dockerfile is used by CI's Trivy scan
# (.github/workflows/ci.yml) and production deploys (.github/workflows/
# deploy.yml) only. See MANUAL_INTEGRATION_NOTES.md for the equivalent
# local (non-Docker) dev setup this same cross-import now requires.
#
# Build from repo root:
#   docker build -f api-gateway/Dockerfile -t pvh-api:latest .
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (Docker layer cache)
COPY api-gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rag-engine/requirements.txt ./rag-engine-requirements.txt
RUN pip install --no-cache-dir -r rag-engine-requirements.txt

COPY vector-store/requirements.txt ./vector-store-requirements.txt
RUN pip install --no-cache-dir -r vector-store-requirements.txt

# Copy source
COPY api-gateway/src/ ./src/
COPY api-gateway/migrations/ ./migrations/
COPY api-gateway/alembic.ini .
COPY rag-engine/src/ ./rag_engine/
COPY vector-store/src/ ./vector_store/

# Non-root user for security
RUN adduser --disabled-password --gecos "" pvhuser
USER pvhuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
