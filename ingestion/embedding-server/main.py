"""
Clinical-BERT Embedding Server — Phase 1 stub.
Full implementation loaded at Phase 5.
Returns a 200 /health immediately so other services can start.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

MODEL_NAME = os.getenv("MODEL_NAME", "emilyalsentzer/Bio_ClinicalBERT")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "32"))
log = logging.getLogger(__name__)

_tokenizer = None
_model = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tokenizer, _model
    log.info("Loading model: %s", MODEL_NAME)
    try:
        from transformers import AutoTokenizer, AutoModel
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        _model = AutoModel.from_pretrained(MODEL_NAME)
        _model.eval()
        log.info("Model loaded — batch_size=%d", BATCH_SIZE)
    except Exception as e:
        log.warning("Model load failed (stub mode): %s", e)
    yield


app = FastAPI(title="PVH Embedding Server", version="1.0.0", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str]


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    import torch
    if _model is None or _tokenizer is None:
        # Phase 1 stub: return zero vectors
        return EmbedResponse(
            embeddings=[[0.0] * 768 for _ in req.texts],
            model=f"{MODEL_NAME}:stub",
        )
    all_vecs = []
    for i in range(0, len(req.texts), BATCH_SIZE):
        batch = req.texts[i: i + BATCH_SIZE]
        inputs = _tokenizer(
            batch, return_tensors="pt",
            truncation=True, max_length=512, padding=True,
        )
        with torch.no_grad():
            out = _model(**inputs)
        mask = inputs["attention_mask"].unsqueeze(-1).float()
        vecs = (out.last_hidden_state * mask).sum(1) / mask.sum(1)
        all_vecs.extend(vecs.tolist())
    return EmbedResponse(embeddings=all_vecs, model=MODEL_NAME)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "healthy",
        "model": MODEL_NAME,
        "ready": _model is not None,
    }
