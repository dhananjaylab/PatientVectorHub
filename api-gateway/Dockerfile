FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Non-root user for security
RUN adduser --disabled-password --gecos "" pvhuser
USER pvhuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
