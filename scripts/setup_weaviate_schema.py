#!/usr/bin/env python3
"""
Create Weaviate PatientDocument collections for all tenants.
Safe to run multiple times - skips existing collections.
"""
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "8080"))

# Use seeded tenant IDs from seed_data.py
TENANT_IDS = [
    "00000000-0000-0000-0000-000000000001",  # Acme Health
    "00000000-0000-0000-0000-000000000002",  # Riverside Medical
]


def collection_name(tenant_id: str) -> str:
    return f"PatientDocument_{tenant_id.replace('-', '_')}"


def resolve_weaviate_target() -> tuple[dict[str, str | int], str, bool]:
    weaviate_url = (os.getenv("WEAVIATE_URL") or "").strip()
    weaviate_api_key = (os.getenv("WEAVIATE_API_KEY") or "").strip()

    if weaviate_url:
        if "://" not in weaviate_url:
            weaviate_url = f"https://{weaviate_url}"
        parsed = urlparse(weaviate_url)
        target_label = parsed.netloc or weaviate_url
        client_kwargs: dict[str, str | int] = {"cluster_url": weaviate_url}
        if weaviate_api_key:
            client_kwargs["api_key"] = weaviate_api_key
        return client_kwargs, target_label, True

    return {"host": WEAVIATE_HOST, "port": WEAVIATE_PORT}, f"{WEAVIATE_HOST}:{WEAVIATE_PORT}", False


def create_schema() -> None:
    try:
        import weaviate
        from weaviate.classes.config import (
            Configure, Property, DataType, VectorDistances,
        )
    except ImportError:
        print("  weaviate-client not installed - skipping schema setup")
        return

    # Determine which vector index type to use based on whether we're using cloud
    is_cloud = bool((os.getenv("WEAVIATE_URL") or "").strip())

    client_kwargs, target_label, use_cloud = resolve_weaviate_target()

    # Wait for Weaviate to be ready
    for attempt in range(12):
        try:
            if use_cloud:
                from weaviate.classes.init import Auth
                client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=client_kwargs["cluster_url"],
                    auth_credentials=Auth.api_key(client_kwargs["api_key"]) if client_kwargs.get("api_key") else None,
                )
            else:
                client = weaviate.connect_to_local(
                    host=client_kwargs["host"], port=client_kwargs["port"],
                )
            if client.is_ready():
                break
            client.close()
        except Exception as e:
            if attempt == 11:
                print(f"  ERROR Weaviate not ready at {target_label}: {e}")
                return
            print(f"  Waiting for Weaviate... ({attempt + 1}/12)")
            time.sleep(5)
    
    # Determine vector index configuration based on whether we're using cloud
    if use_cloud:
        # Weaviate cloud uses flat index (hfresh is server-side only)
        vector_config = Configure.VectorIndex.flat(
            distance_metric=VectorDistances.COSINE,
        )
    else:
        # Local Weaviate uses hnsw
        vector_config = Configure.VectorIndex.hnsw(
            ef=128,
            ef_construction=256,
            max_connections=64,
            distance_metric=VectorDistances.COSINE,
        )

    existing = {c.name for c in client.collections.list_all().values()}

    for tid in TENANT_IDS:
        name = collection_name(tid)
        if name in existing:
            print(f"  OK Exists  : {name}")
            continue

        client.collections.create(
            name=name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_config=vector_config,
            properties=[
                Property(name="chunk_text", data_type=DataType.TEXT),
                Property(name="document_id", data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="patient_id_hash", data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="document_type", data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="model_version", data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="chunk_index", data_type=DataType.INT),
            ],
        )
        print(f"  OK Created : {name}")

    client.close()


if __name__ == "__main__":
    _, target_label, _ = resolve_weaviate_target()
    print(f"Setting up Weaviate schemas on {target_label}...")
    create_schema()
    print("Done.")
