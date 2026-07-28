# ADR-012: Hugging Face-Hosted Clinical Embedding Server (Phase 5) — Managed Inference Endpoints, Not Local Docker

**Date:** 2026-07-26
**Status:** Accepted
**Relates to:** ADR-009 (supersedes its "parked" framing of Phase 5, not its OpenAI-default
decision), `ingestion/embedding-server/`, `ingestion/src/embeddings/clinical_bert_embedder.py`,
`ingestion/src/embeddings/__init__.py`, `scripts/deploy_hf_embedding_endpoint.py`,
`ingestion/src/config.py`

## Context

ADR-009 picked OpenAI `text-embedding-3-large` as the Phase 4 default and explicitly parked
the self-hosted clinical-bert path — `ingestion/embedding-server/main.py` shipped as a stub
that loads `emilyalsentzer/Bio_ClinicalBERT` if present and otherwise returns zero vectors,
with a Dockerfile intended to run it as a local/K8s FastAPI pod. ADR-009 was explicit that
this reversal was for **synthetic-data development only**, and that the self-hosted path
needed to come back before real PHI ingestion.

This ADR builds that path for real, on explicit direction, with one change from the original
plan: **no Docker, no self-managed container.** Model hosting and inference both run on
Hugging Face's Inference Endpoints product instead of a container we build, deploy, and
operate ourselves.

Two sub-decisions fell out of that: which model, and how it's actually deployed/called.

## Decision

### 1. Model: `NeuML/pubmedbert-base-embeddings`, not raw `Bio_ClinicalBERT`

`emilyalsentzer/Bio_ClinicalBERT` is a masked-language-model checkpoint — it was never
trained with a sentence-embedding or retrieval objective, and it benchmarks accordingly
poorly for that use. Published MTEB-style medical benchmarks (Falis et al., "Med-gte-hybrid,"
arXiv:2502.15996) score raw ClinicalBERT at 25.2 (Mayo STS) / 59.8 (BIOSSES), against 65–90
for purpose-trained embedding models on the same tasks. Mean-pooling its raw hidden states
(what the parked `main.py` stub did) would have shipped a working-but-mediocre retriever.

`NeuML/pubmedbert-base-embeddings` is PubMedBERT fine-tuned specifically for sentence
embeddings via `sentence-transformers`, Apache-2.0 licensed, 768-dim, and — the detail that
made it the practical choice for this ADR — already tagged `text-embeddings-inference` on
the Hub. That means Hugging Face's TEI serving container recognizes its pooling config
out of the box; no custom inference handler needed to get correct mean-pooled embeddings out
of it. A Matryoshka variant (`-matryoshka`, dynamic 64–768 dim) exists if a smaller footprint
is wanted later.

`CLINICAL_BERT_MODEL_ID` is a config value, not a hardcoded import — swapping models later
(e.g. to a MedCPT or BioLORD variant) doesn't require code changes, only a re-deploy of the
endpoint and a re-embed.

### 2. Hosting: Hugging Face Inference Endpoints (dedicated), TEI container

Deployed via `huggingface_hub.create_inference_endpoint()` (`scripts/
deploy_hf_embedding_endpoint.py`), requesting the Text Embeddings Inference container type.
Hugging Face builds, runs, health-checks, and autoscales the container — including
scale-to-zero when idle (configurable; ~20–30s cold-start on first request per HF's own
docs) or `min_replica=1` to keep a warm replica if that latency isn't acceptable.

This directly resolves the risk the pre-implementation brainstorm doc's risk register flagged
under "clinical-bert pod slow to start (>60s) — blocks ingestion workers on boot": there is no
pod we boot anymore, and TEI's own images boot fast by design.

`ingestion/embedding-server/`'s `Dockerfile` and local `main.py` FastAPI wrapper are retired —
see Consequences. `docker-compose.yml`'s `embedding-model` service and `deploy.yml`'s
`pvh-embedding` image build/push are removed for the same reason: there's no image to build.

### 3. Client: `huggingface_hub.AsyncInferenceClient`, lazily constructed

`ingestion/src/embeddings/clinical_bert_embedder.py` mirrors `openai_embedder.py`'s exact
shape from Phase 4: a module-level `_client: AsyncInferenceClient | None = None`, a
`_get_client()` that constructs it on first use (not at import time — same reasoning as
`openai_embedder.py`'s `_get_client()` docstring: constructing a client eagerly at import
time with an empty/misconfigured token turns "no `HF_TOKEN` set yet" into an import-time
crash instead of a first-call error), a `tenacity` retry wrapper, and an `embed_batch(texts)
-> list[list[float]]` function with the same batching behavior. `AsyncInferenceClient(model=
settings.HF_EMBEDDING_ENDPOINT_URL, token=settings.HF_TOKEN)` — passing the deployed
endpoint's full URL as `model` sends requests directly to it, bypassing HF's serverless
multi-provider routing (that routing is for the shared Inference Providers marketplace, not
for a dedicated endpoint you're paying for).

### 4. Provider routing is now real, not a dead config field

`EMBEDDING_PROVIDER` existed in `ingestion/src/config.py` since Phase 4 but nothing read it —
`batch_worker.py` imported `openai_embedder.embed_batch` directly. `ingestion/src/embeddings/
__init__.py` now exposes a single `embed_batch()` that dispatches on `settings
.EMBEDDING_PROVIDER` (`"openai"` | `"clinical_bert"`), and `batch_worker.py`'s import changed
from `from ..embeddings.openai_embedder import embed_batch` to `from ..embeddings import
embed_batch` — a one-line change to already-tested Phase 4 code. **The default stays
`openai`.** This ADR makes the alternate path real and switchable; it does not flip the
default.

### 5. The BAA guardrail extends to this path too

ADR-009's `ALLOW_REAL_PHI` / `PHI_BAA_ACKNOWLEDGED` guardrail in `config.py`'s
`model_post_init` only checked `EMBEDDING_PROVIDER == "openai"`. It now also covers
`"clinical_bert"`. This matters because a dedicated HF Inference Endpoint is still Hugging
Face's cloud infrastructure — "self-hosted" in the original Phase 5 framing meant *our own
VPC*; a dedicated-but-managed endpoint is not that. PHI still leaves the org's network
boundary to reach it. Real PHI on this path needs either a Hugging Face Enterprise BAA or a
private-networking deployment (HF supports this on Enterprise plans) before it's any safer
than the OpenAI path — it is not a compliance shortcut, just a different vendor.

### 6. Dimension mismatch is a real constraint, not just documentation

`clinical_bert` embeddings are 768-dim; the OpenAI path is 1536-dim (Matryoshka-shortened,
per ADR-009). These are not interchangeable inside one Weaviate/Qdrant collection. Switching
the active default provider later is a re-embed-and-recreate-collection operation, not a
live cutover. `CLINICAL_BERT_DIMENSIONS=768` is tracked as its own config value rather than
overloading `EMBEDDING_DIMENSIONS` so Phase 6's Qdrant collection setup can read the value
that actually matches whichever provider is active. Flagged for the Phase 6 vector-store work,
not resolved by this ADR.

## Consequences

- No container we build or operate for embeddings inference; Hugging Face's TEI image is
  purpose-built for this and handles batching/throughput itself. HF's own published TEI
  benchmark (`BAAI/bge-base-en-v1.5` on an A10G) reports 450+ req/sec and roughly 64x lower
  cost per token than calling a general-purpose LLM provider's embeddings API — directionally
  relevant here even though our model and hardware choice will differ.
- New external dependency and failure domain: ingestion now depends on Hugging Face's
  Inference Endpoints uptime when `EMBEDDING_PROVIDER=clinical_bert`, same as it already
  depends on OpenAI's uptime when set to `openai`. `clinical_bert_embedder.py`'s retry
  wrapper covers transient failures; it doesn't cover an extended HF outage.
- Provisioning the endpoint is a manual, outside-of-CI step (`scripts/
  deploy_hf_embedding_endpoint.py`, run by an operator with a funded HF account) — it is not
  created automatically by `make dev` or any CI job, unlike everything else in the Docker
  Compose stack. `HF_EMBEDDING_ENDPOINT_URL` must be filled in after deployment.
- `ingestion/embedding-server/Dockerfile` and `requirements.txt` are deleted.
  `ingestion/embedding-server/main.py` is replaced with a short pointer document — see that
  directory's `README.md`.
- Docs 02 (TRD), 05, and 06's Phase 5 description ("clinical-bert FastAPI pod... Docker
  image") should be read as superseded by this ADR for the hosting mechanism; the model
  identity and embedding intent survive, the Docker delivery mechanism does not.

## References

- `docs/adr/ADR-009-aiven-openai-native-multitenancy-pivot.md`
- `docs/PHASE_5_IMPLEMENTATION_PLAN.md`
- Hugging Face — Inference Endpoints embedding tutorial:
  https://huggingface.co/docs/inference-endpoints/en/tutorials/embedding
- Hugging Face — `huggingface_hub` Inference Endpoints guide (`create_inference_endpoint`):
  https://huggingface.co/docs/huggingface_hub/guides/inference_endpoints
- Hugging Face — TEI-powered embedding endpoints blog post (throughput/cost figures cited
  above): https://github.com/huggingface/blog/blob/main/inference-endpoints-embeddings.md
- Model card: https://huggingface.co/NeuML/pubmedbert-base-embeddings
- Falis et al., "Med-gte-hybrid," arXiv:2502.15996 (ClinicalBERT vs. purpose-trained
  embedding model MTEB-style scores cited in §1)
