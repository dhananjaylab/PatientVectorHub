FROM python:3.11-slim

# System dependencies for PyMuPDF and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev \
    libfreetype6-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN adduser --disabled-password --gecos "" pvhuser
USER pvhuser

CMD ["celery", "-A", "src.workers.batch_worker.celery_app", "worker",
     "--loglevel=info", "--queues=doc-ingest", "-c", "4"]
