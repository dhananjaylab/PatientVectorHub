# ── PatientVectorHub — ingestion service image ────────────────────────────────
# Phase 4 change: this Dockerfile now expects to be built with the REPO ROOT
# as build context, not ./ingestion — e.g.
#   docker build -f ingestion/Dockerfile -t pvh-ingestion .
# (docker-compose.yml's celery-worker/celery-beat/kafka-consumer services are
# already set up this way: `context: .`, `dockerfile: ingestion/Dockerfile`).
#
# Why: process_document() imports `vector_store.interface`
# (ingestion/src/workers/batch_worker.py) — the vector-store service's src/
# tree needs to be baked into this image under a top-level `vector_store`
# package name, and Docker cannot COPY from outside its build context. The
# per-service-venv layout in this repo's README doesn't hit this problem for
# local (non-Docker) dev — see MANUAL_INTEGRATION_NOTES.md for the equivalent
# `pip install -e` / PYTHONPATH step needed there.
FROM python:3.11-slim

# System dependencies for PyMuPDF and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    libfreetype6-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ingestion/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vector-store/requirements.txt ./vector-store-requirements.txt
RUN pip install --no-cache-dir -r vector-store-requirements.txt

COPY ingestion/src/ ./src/
COPY vector-store/src/ ./vector_store/

RUN adduser --disabled-password --gecos "" pvhuser
USER pvhuser

# Default command runs the Celery worker. celery-beat and the Kafka stream
# consumer override `command:` in docker-compose.yml to reuse this same image.
CMD ["celery", "-A", "src.workers.celery_app.celery_app", "worker",
     "--loglevel=info", "--queues=doc-ingest", "-c", "4"]
