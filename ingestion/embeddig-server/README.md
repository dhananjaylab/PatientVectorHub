# `ingestion/embedding-server/` — retired (ADR-012)

This directory used to hold a local FastAPI + `transformers`/`torch`
wrapper around `emilyalsentzer/Bio_ClinicalBERT`, built as a Docker image
(`docker-compose.yml`'s old `embedding-model` service, `deploy.yml`'s old
`pvh-embedding` image build/push) and served through a hand-rolled
`/embed` + `/health` API.

That approach is retired as of Phase 5 / ADR-012. The clinical embedding
path now runs entirely on **Hugging Face Inference Endpoints** — Hugging
Face builds, hosts, health-checks, and autoscales the serving container
(Text Embeddings Inference); nothing here builds or runs a container of
our own. It also switched models, from a raw MLM checkpoint
(`Bio_ClinicalBERT`) to one actually trained for embeddings
(`NeuML/pubmedbert-base-embeddings`) — see ADR-012 for the benchmark
reasoning.

What replaced this directory's contents:

| Old                                | New                                                                 |
|-------------------------------------|----------------------------------------------------------------------|
| `Dockerfile`, local `main.py`       | Hugging Face Inference Endpoint, provisioned by `scripts/deploy_hf_embedding_endpoint.py` |
| Direct HTTP call to `localhost:8001`| `ingestion/src/embeddings/clinical_bert_embedder.py` (`huggingface_hub.AsyncInferenceClient`) |
| `EMBEDDING_MODEL_URL` env var       | `HF_EMBEDDING_ENDPOINT_URL`, `HF_TOKEN`, `CLINICAL_BERT_MODEL_ID` in `.env` |

The old `main.py` is still visible in git history at this path if you need
to reference the manual mean-pooling implementation it used
(`git log --follow -- ingestion/embedding-server/main.py`).

See `docs/adr/ADR-012-hf-hosted-clinical-bert-embedding-server.md` and
`docs/PHASE_5_IMPLEMENTATION_PLAN.md` for the full decision record.
