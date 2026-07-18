#!/usr/bin/env python3
"""
Create Qdrant collections for all tenants (DR vector store).
Safe to run multiple times - skips existing collections.
"""
import os
from pathlib import Path
import time

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6334"))

TENANT_IDS = [
    "00000000-0000-0000-0000-000000000001",
    "00000000-0000-0000-0000-000000000002",
]


def collection_name(tenant_id: str) -> str:
    return f"patient_docs_{tenant_id.replace('-', '_')}"


def create_collections() -> None:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import (
            Distance, VectorParams, HnswConfigDiff,
        )
    except ImportError:
        print("  qdrant-client not installed - skipping Qdrant setup")
        return

    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")

    for attempt in range(12):
        try:
            if qdrant_url and qdrant_api_key:
                client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=10)
            else:
                client = QdrantClient(host=QDRANT_HOST, port=6333, timeout=10)
            client.get_collections()
            break
        except Exception as e:
            if attempt == 11:
                target_str = qdrant_url if (qdrant_url and qdrant_api_key) else QDRANT_HOST
                print(f"  ERROR Qdrant not ready at {target_str}: {e}")
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
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            hnsw_config=HnswConfigDiff(m=64, ef_construct=256),
        )
        client.create_payload_index(name, "document_id",   "keyword")
        client.create_payload_index(name, "document_type", "keyword")
        client.create_payload_index(name, "model_version", "keyword")
        print(f"  OK Created : {name}")


if __name__ == "__main__":
    print(f"Setting up Qdrant collections on {QDRANT_HOST}...")
    create_collections()
    print("Done.")
