"""
Retriever — Phase 7's first real caller of vector_store.interface.search()
(ADR-013 §1 flagged this gap; this closes it).

Deliberately thin: embed the query, call get_store(tenant_id).search().
No separate BM25/RRF layer here — WeaviateStore.search() already does
native hybrid (BM25 + vector) search server-side (Phase 6), which covers
the default/primary path. See docs/adr/ADR-014-rag-query-engine.md §2
for why a standalone BM25 index was scoped out of this phase rather than
just not mentioned.
"""

from vector_store.interface import SearchResult, get_store

from .query_embedder import embed_query


async def retrieve(
    tenant_id: str, query_text: str, top_k: int = 10, filters: dict | None = None
) -> list[SearchResult]:
    """Embed query_text and return the top_k most relevant chunks for
    tenant_id. filters is passed straight through to vector_store — see
    vector_store/src/weaviate_store.py's _build_filter() for the current
    (document_types-only) filter surface.

    The explicit `results:` annotation below isn't decorative: mypy can't
    statically resolve `vector_store` as a package (same cross-package
    naming gap tests/conftest.py's _ensure_cross_package_alias() works
    around at runtime — mypy has no equivalent, and --ignore-missing-imports
    just makes it treat the whole import as Any instead of erroring).
    Without this, `warn_return_any` (enabled in pyproject.toml) flags this
    function for silently returning Any where list[SearchResult] is
    declared — this is the first function in the repo that both crosses
    into vector_store *and* declares a concrete return type, so it's the
    first place this pre-existing gap actually surfaces."""
    query_vector = await embed_query(query_text)
    store = get_store(tenant_id)
    results: list[SearchResult] = await store.search(
        query_text, query_vector, top_k=top_k, filters=filters
    )
    return results
