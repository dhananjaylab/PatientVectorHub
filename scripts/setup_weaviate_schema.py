#!/usr/bin/env python3
"""
Create Weaviate PatientDocument collections for all tenants.
Safe to run multiple times - skips existing collections.
"""
import os
from pathlib import Path
import sys
import time

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


def create_schema() -> None:
    try:
        import weaviate
        from weaviate.classes.config import (
            Configure, Property, DataType, VectorDistances,
        )
    except ImportError:
        print("  weaviate-client not installed - skipping schema setup")
        return

    weaviate_url = os.getenv("WEAVIATE_URL")
    weaviate_api_key = os.getenv("WEAVIATE_API_KEY")

    # Wait for Weaviate to be ready
    for attempt in range(12):
        try:
            if weaviate_url and weaviate_api_key:
                from weaviate.classes.init import Auth
                client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=weaviate_url,
                    auth_credentials=Auth.api_key(weaviate_api_key),
                )
            else:
                client = weaviate.connect_to_local(
                    host=WEAVIATE_HOST, port=WEAVIATE_PORT,
                )
            if client.is_ready():
                break
            client.close()
        except Exception as e:
            if attempt == 11:
                target_str = weaviate_url if (weaviate_url and weaviate_api_key) else f"{WEAVIATE_HOST}:{WEAVIATE_PORT}"
                print(f"  ERROR Weaviate not ready at {target_str}: {e}")
                return
            print(f"  Waiting for Weaviate... ({attempt + 1}/12)")
            time.sleep(5)


    existing = {c.name for c in client.collections.list_all().values()}

    for tid in TENANT_IDS:
        name = collection_name(tid)
        if name in existing:
            print(f"  OK Exists  : {name}")
            continue

        client.collections.create(
            name=name,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                ef=128,
                ef_construction=256,
                max_connections=64,
                distance_metric=VectorDistances.COSINE,
            ),
            properties=[
                Property(name="chunk_text",      data_type=DataType.TEXT),
                Property(name="document_id",     data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="patient_id_hash", data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="document_type",   data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="model_version",   data_type=DataType.TEXT,
                         index_filterable=True, index_searchable=False),
                Property(name="chunk_index",     data_type=DataType.INT),
            ],
        )
        print(f"  OK Created : {name}")

    client.close()


if __name__ == "__main__":
    print(f"Setting up Weaviate schemas on {WEAVIATE_HOST}:{WEAVIATE_PORT}...")
    create_schema()
    print("Done.")
