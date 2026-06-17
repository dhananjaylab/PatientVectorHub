FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

ENV MODEL_NAME=emilyalsentzer/Bio_ClinicalBERT
ENV BATCH_SIZE=32
ENV PORT=8001

RUN adduser --disabled-password --gecos "" pvhuser
USER pvhuser

EXPOSE 8001

# Pre-download model at build time so startup is fast
RUN python -c "from transformers import AutoTokenizer, AutoModel; \
    AutoTokenizer.from_pretrained('emilyalsentzer/Bio_ClinicalBERT'); \
    AutoModel.from_pretrained('emilyalsentzer/Bio_ClinicalBERT')" || true

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
