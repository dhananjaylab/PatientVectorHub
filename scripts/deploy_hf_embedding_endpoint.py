#!/usr/bin/env python3
"""
Deploy, inspect, and manage the Hugging Face Inference Endpoint that serves
CLINICAL_BERT_MODEL_ID for the "clinical_bert" embedding provider
(ADR-012). Requests a Text Embeddings Inference (TEI) container — Hugging
Face builds, runs, health-checks, and autoscales it. There is no Docker
image of ours involved anywhere in this path.

This is a manual, outside-of-CI operator step, unlike
scripts/create_kafka_topics.py or scripts/setup_weaviate_schema.py — it
provisions a billed cloud resource on your Hugging Face account, so it is
deliberately not wired into `make dev` or any CI job. Run it once per
environment after HF_TOKEN is set in .env, then copy the printed endpoint
URL into HF_EMBEDDING_ENDPOINT_URL.

Usage:
    python scripts/deploy_hf_embedding_endpoint.py create
    python scripts/deploy_hf_embedding_endpoint.py status
    python scripts/deploy_hf_embedding_endpoint.py pause
    python scripts/deploy_hf_embedding_endpoint.py resume
    python scripts/deploy_hf_embedding_endpoint.py delete

`create` is idempotent — if an endpoint named HF_EMBEDDING_ENDPOINT_NAME
already exists in your namespace, it's reused rather than re-created.

See docs/PHASE_5_IMPLEMENTATION_PLAN.md and docs/adr/
ADR-012-hf-hosted-clinical-bert-embedding-server.md for the reasoning
behind the model and hosting choices below.
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_NAMESPACE = os.getenv("HF_NAMESPACE") or None  # None = your personal account
ENDPOINT_NAME = os.getenv("HF_EMBEDDING_ENDPOINT_NAME", "pvh-clinical-embeddings")
MODEL_ID = os.getenv("CLINICAL_BERT_MODEL_ID", "NeuML/pubmedbert-base-embeddings")

# Deployment defaults — override via env if your HF org has different
# quota/region access. A 768-dim BERT-base embedding model doesn't need a
# GPU at PVH's expected ingestion throughput; set HF_ENDPOINT_ACCELERATOR=
# gpu if you need higher throughput than a CPU instance gives you.
ACCELERATOR = os.getenv("HF_ENDPOINT_ACCELERATOR", "cpu")  # "cpu" | "gpu"
VENDOR = os.getenv("HF_ENDPOINT_VENDOR", "aws")
REGION = os.getenv("HF_ENDPOINT_REGION", "us-east-1")
INSTANCE_TYPE = os.getenv(
    "HF_ENDPOINT_INSTANCE_TYPE", "intel-icl" if ACCELERATOR == "cpu" else "nvidia-a10g"
)
INSTANCE_SIZE = os.getenv("HF_ENDPOINT_INSTANCE_SIZE", "x2")
# min_replica=0 (default) means scale-to-zero: ~20-30s cold start on the
# first request after idle, per Hugging Face's own docs (ADR-012
# Consequences). Set HF_ENDPOINT_MIN_REPLICA=1 to keep a warm replica if
# that latency isn't acceptable for your use case.
MIN_REPLICA = int(os.getenv("HF_ENDPOINT_MIN_REPLICA", "0"))
MAX_REPLICA = int(os.getenv("HF_ENDPOINT_MAX_REPLICA", "1"))


def _require_token() -> None:
    if not HF_TOKEN:
        print("ERROR: HF_TOKEN is not set (.env or environment).")
        print("       Create a token at https://huggingface.co/settings/tokens")
        print("       (needs 'Write' access to manage Inference Endpoints).")
        sys.exit(1)


def _find_existing():
    from huggingface_hub import list_inference_endpoints

    for ep in list_inference_endpoints(namespace=HF_NAMESPACE or "*", token=HF_TOKEN):
        if ep.name == ENDPOINT_NAME:
            return ep
    return None


def create() -> None:
    from huggingface_hub import create_inference_endpoint
    from huggingface_hub.errors import InferenceEndpointTimeoutError

    _require_token()
    existing = _find_existing()
    if existing is not None:
        print(
            f"  Endpoint '{ENDPOINT_NAME}' already exists (status={existing.status}) — reusing it."
        )
        _print_url(existing)
        return

    print(f"  Creating endpoint '{ENDPOINT_NAME}' for model '{MODEL_ID}'...")
    print(
        f"  vendor={VENDOR} region={REGION} accelerator={ACCELERATOR} "
        f"instance_type={INSTANCE_TYPE} instance_size={INSTANCE_SIZE} "
        f"min_replica={MIN_REPLICA} max_replica={MAX_REPLICA}"
    )

    endpoint = create_inference_endpoint(
        ENDPOINT_NAME,
        namespace=HF_NAMESPACE,
        repository=MODEL_ID,
        framework="pytorch",
        task="sentence-embeddings",  # TEI container — see ADR-012 §1/§2
        accelerator=ACCELERATOR,
        vendor=VENDOR,
        region=REGION,
        instance_type=INSTANCE_TYPE,
        instance_size=INSTANCE_SIZE,
        min_replica=MIN_REPLICA,
        max_replica=MAX_REPLICA,
        type="protected",  # requires a bearer token on every request — not public
        token=HF_TOKEN,
    )

    print("  Waiting for the endpoint to come online (can take a few minutes on first deploy)...")
    try:
        endpoint.wait(timeout=600)
    except InferenceEndpointTimeoutError:
        print("  Still deploying after 10 minutes — this is normal for a first-time image pull.")
        print(f"  Re-run: python {Path(__file__).name} status")
        return
    _print_url(endpoint)


def status() -> None:
    _require_token()
    from huggingface_hub import get_inference_endpoint

    endpoint = _find_existing()
    if endpoint is None:
        print(f"  No endpoint named '{ENDPOINT_NAME}' found. Run `create` first.")
        return
    endpoint = get_inference_endpoint(ENDPOINT_NAME, namespace=endpoint.namespace, token=HF_TOKEN)
    print(f"  name={endpoint.name} namespace={endpoint.namespace} status={endpoint.status}")
    print(f"  url={endpoint.url or '(not ready yet)'}")


def pause() -> None:
    _act_on_existing(lambda ep: ep.pause(), "paused")


def resume() -> None:
    _act_on_existing(lambda ep: ep.resume(), "resumed")


def delete() -> None:
    _act_on_existing(lambda ep: ep.delete(), "deleted")


def _act_on_existing(fn, verb: str) -> None:
    _require_token()
    endpoint = _find_existing()
    if endpoint is None:
        print(f"  No endpoint named '{ENDPOINT_NAME}' found — nothing to do.")
        return
    fn(endpoint)
    print(f"  Endpoint '{ENDPOINT_NAME}' {verb}.")


def _print_url(endpoint) -> None:
    if endpoint.url:
        print(f"  Endpoint ready: {endpoint.url}")
        print(f"  Set in .env:    HF_EMBEDDING_ENDPOINT_URL={endpoint.url}")
        print("  Then set:       EMBEDDING_PROVIDER=clinical_bert")
    else:
        print(f"  Endpoint status={endpoint.status} — not ready yet. Re-run `status` shortly.")


ACTIONS = {"create": create, "status": status, "pause": pause, "resume": resume, "delete": delete}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=sorted(ACTIONS))
    args = parser.parse_args()
    ACTIONS[args.action]()
