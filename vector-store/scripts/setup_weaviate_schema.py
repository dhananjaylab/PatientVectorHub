#!/usr/bin/env python3
"""
Create the shared Weaviate PatientDocument collection with native multi-tenancy.

Multi-tenancy strategy
----------------------
One collection, shard-level tenant isolation enforced by Weaviate.
Tenants self-register on first ``collection.with_tenant(tenant_id)`` call
(auto_tenant_creation=True), so no TENANT_IDS seed loop is needed here.

Safe to run multiple times — skips creation if the collection already exists.
"""
import os
from pathlib import Path
import time
from urllib.parse import urlparse

from dotenv import load_dotenv

try:
    from weaviate.classes.config import Configure, DataType, Property, VectorDistances
except ImportError:  # pragma: no cover - handled gracefully at runtime
    Configure = None
    DataType = None
    Property = None
    VectorDistances = None

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "8080"))

# Single shared collection — tenant isolation is handled by Weaviate natively.
COLLECTION_NAME = "PatientDocument"


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


def build_vector_index_config(use_cloud: bool, configure_module=None, vector_distances=None):
    """
    Return the appropriate vector index config for the target environment.

    * Cloud (Weaviate Cloud):  hfresh — the only index type permitted.
    * Local (self-hosted):     hnsw  — standard HNSW with explicit tuning params.
    """
    configure_module = configure_module or Configure
    vector_distances_module = vector_distances or VectorDistances

    if configure_module is None or vector_distances_module is None:
        raise RuntimeError("weaviate-client is not available")

    if use_cloud:
        return configure_module.VectorIndex.hfresh(
            distance_metric=vector_distances_module.COSINE,
        )

    return configure_module.VectorIndex.hnsw(
        ef=128,
        ef_construction=256,
        max_connections=64,
        distance_metric=vector_distances_module.COSINE,
    )


def create_schema() -> None:
    try:
        import weaviate
    except ImportError:
        print("  weaviate-client not installed - skipping schema setup")
        return

    if Configure is None or Property is None or DataType is None or VectorDistances is None:
        print("  weaviate-client config API not available - skipping schema setup")
        return

    client_kwargs, target_label, use_cloud = resolve_weaviate_target()
    client = None

    try:
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
                client = None
            except Exception as e:
                if attempt == 11:
                    print(f"  ERROR Weaviate not ready at {target_label}: {e}")
                    return
                print(f"  Waiting for Weaviate... ({attempt + 1}/12)")
                time.sleep(5)

        if client is None:
            print(f"  ERROR Weaviate connection could not be established at {target_label}")
            return

        existing = {c.name for c in client.collections.list_all().values()}

        if COLLECTION_NAME in existing:
            print(f"  OK Exists  : {COLLECTION_NAME}")
            return

        index_config = build_vector_index_config(
            use_cloud=use_cloud,
            configure_module=Configure,
            vector_distances=VectorDistances,
        )

        client.collections.create(
            name=COLLECTION_NAME,
            # Native multi-tenancy: one collection, one shard per tenant.
            # auto_tenant_creation=True means callers do not need to pre-register
            # tenants — they are created on first collection.with_tenant(id) use.
            multi_tenancy_config=Configure.multi_tenancy(
                enabled=True,
                auto_tenant_creation=True,
            ),
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=index_config,
            ),
            properties=[
                Property(name="chunk_text",      data_type=DataType.TEXT),
                Property(name="document_id",     data_type=DataType.TEXT,
                         index_filterable=True,  index_searchable=False),
                Property(name="patient_id_hash", data_type=DataType.TEXT,
                         index_filterable=True,  index_searchable=False),
                Property(name="document_type",   data_type=DataType.TEXT,
                         index_filterable=True,  index_searchable=False),
                Property(name="model_version",   data_type=DataType.TEXT,
                         index_filterable=True,  index_searchable=False),
                Property(name="chunk_index",     data_type=DataType.INT),
            ],
        )
        print(f"  OK Created : {COLLECTION_NAME}")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    _, target_label, _ = resolve_weaviate_target()
    print(f"Setting up Weaviate schemas on {target_label}...")
    create_schema()
    print("Done.")
