#!/usr/bin/env python3
"""
Create Qdrant collections for all tenants (DR vector store).
Safe to run multiple times - skips existing collections.
"""
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6334"))

# Was hardcoded to 768 (a leftover from the pre-ADR-009 self-hosted
# clinical-bert plan, which used 768-dim embeddings). ADR-009 moved
# embeddings to OpenAI text-embedding-3-large; EMBEDDING_DIMENSIONS is the
# single source of truth for the chosen (possibly shortened, via OpenAI's
# `dimensions` param) vector size — see vector-store/src/config.py for the
# full rationale on the 1536 default. Changing this after any vectors have
# been written requires re-embedding, since Qdrant collections have a fixed
# vector size once created.
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

TENANT_IDS = [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
]


def collection_name(tenant_id: str) -> str:
    return f"patient_docs_{tenant_id.replace('-', '_')}"


def resolve_qdrant_target() -> tuple[dict[str, object], str]:
    qdrant_url = (os.getenv("QDRANT_URL") or "").strip()
    qdrant_api_key = (os.getenv("QDRANT_API_KEY") or "").strip()

    if qdrant_url:
        if "://" not in qdrant_url:
            qdrant_url = f"https://{qdrant_url}"
        parsed = urlparse(qdrant_url)
        target_label = parsed.netloc or qdrant_url
        client_kwargs = {"url": qdrant_url, "timeout": 10}
        if qdrant_api_key:
            client_kwargs["api_key"] = qdrant_api_key
        return client_kwargs, target_label

    return {"host": QDRANT_HOST, "port": QDRANT_PORT, "timeout": 10}, f"{QDRANT_HOST}:{QDRANT_PORT}"


def create_collections() -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import (
            Distance, VectorParams, HnswConfigDiff,
        )
    except ImportError:
        print("  qdrant-client not installed - skipping Qdrant setup")
        return

    client_kwargs, target_label = resolve_qdrant_target()

    for attempt in range(12):
        try:
            client = QdrantClient(**client_kwargs)
            client.get_collections()
            break
        except Exception as e:
            if attempt == 11:
                print(f"  ERROR Qdrant not ready at {target_label}: {e}")
                return
            print(f"  Waiting for Qdrant... ({attempt + 1}/12)")
            time.sleep(5)

    existing = {c.name for c in client.get_collections().collections}

    for tid in TENANT_IDS:
        name = collection_name(tid)
        if name in existing:
            print(f"  OK Exists  : {name}")
            continue

        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBEDDING_DIMENSIONS, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=64, ef_construct=256),
        )
        client.create_payload_index(name, "document_id", "keyword")
        client.create_payload_index(name, "document_type", "keyword")
        client.create_payload_index(name, "model_version", "keyword")
        print(f"  OK Created : {name} ({EMBEDDING_DIMENSIONS}-dim)")


if __name__ == "__main__":
    _, target_label = resolve_qdrant_target()
    print(f"Setting up Qdrant collections on {target_label} (dim={EMBEDDING_DIMENSIONS})...")
    create_collections()
    print("Done.")
