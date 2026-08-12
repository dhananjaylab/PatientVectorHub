#!/usr/bin/env python3
"""
Migrate tests from centralized tests/ to service-specific directories.
Updates sys.path imports automatically.
"""

import os
import shutil
from pathlib import Path

# Test file mapping: (source_file, destination_service, test_type)
TEST_MOVES = [
    # api-gateway service
    ("test_auth_middleware.py", "api-gateway", "unit"),
    ("test_errors.py", "api-gateway", "unit"),
    ("test_phase1_health.py", "api-gateway", "unit"),
    ("test_query_router.py", "api-gateway", "unit"),
    ("test_rbac.py", "api-gateway", "unit"),
    ("test_seed_data.py", "api-gateway", "unit"),
    ("test_rls_isolation.py", "api-gateway", "integration"),
    ("test_rls_isolation_core_tables.py", "api-gateway", "integration"),
    ("test_stack_connectivity.py", "api-gateway", "integration"),
    
    # ingestion service
    ("test_config.py", "ingestion", "unit"),
    ("test_embeddings_provider_routing.py", "ingestion", "unit"),
    ("test_ingestion_chunker.py", "ingestion", "unit"),
    ("test_ingestion_dlq.py", "ingestion", "unit"),
    ("test_ingestion_embedder.py", "ingestion", "unit"),
    ("test_ingestion_parsers.py", "ingestion", "unit"),
    ("test_llm_router.py", "ingestion", "unit"),
    ("test_ingestion_dlq_end_to_end.py", "ingestion", "integration"),
    ("test_ingestion_end_to_end.py", "ingestion", "integration"),
    
    # vector-store service
    ("test_qdrant_store.py", "vector-store", "unit"),
    ("test_vector_store_factory.py", "vector-store", "unit"),
    ("test_weaviate_schema.py", "vector-store", "unit"),
    ("test_weaviate_search_delete.py", "vector-store", "unit"),
    ("test_dual_write_store.py", "vector-store", "integration"),
    ("test_vector_store_layer.py", "vector-store", "integration"),
    
    # rag-engine service
    ("test_query_embedder.py", "rag-engine", "unit"),
    ("test_rag_synthesizer.py", "rag-engine", "unit"),
    ("test_retriever.py", "rag-engine", "unit"),
    ("test_rag_query_pipeline.py", "rag-engine", "integration"),
    
    # embedding-server service
    ("test_clinical_bert_embedder.py", "embedding-server", "unit"),
    ("test_hf_deploy_script.py", "embedding-server", "unit"),
    ("test_logging.py", "embedding-server", "unit"),
    
    # shared (cross-service)
    ("test_db_models.py", "shared", "unit"),
]


def simplify_sys_path(content: str, service: str) -> str:
    """Replace complex sys.path.insert with simple path configuration."""
    # Old pattern: sys.path.insert(0, os.path.join(..., "service-name"))
    # New pattern: (nothing needed, pytest.ini + PYTHONPATH handles it)
    
    lines = content.split('\n')
    new_lines = []
    skip_next = False
    
    for i, line in enumerate(lines):
        # Skip sys.path.insert lines
        if 'sys.path.insert' in line and 'os.path.join' in line:
            continue
        if 'sys.path.insert' in line and 'dirname' in line:
            continue
        # Skip corresponding imports if they're only used for sys.path setup
        if 'import os' in line and i + 1 < len(lines) and 'sys.path' in lines[i + 1]:
            skip_next = True
            continue
        if skip_next and 'import os' in line:
            skip_next = False
            continue
        new_lines.append(line)
    
    result = '\n'.join(new_lines)
    
    # Clean up extra blank lines at the top
    while result.startswith('\n\n\n'):
        result = result[1:]
    
    return result


def update_imports(content: str, service: str) -> str:
    """Update relative imports if needed."""
    # For most tests, imports stay the same since they import from src
    # Only cross-package imports might need updates
    
    if service == "rag-engine":
        # These might need the cross-package aliases
        pass
    
    return content


def move_test_file(repo_root: str, source: str, service: str, test_type: str) -> bool:
    """Move a test file and update its content."""
    # Source paths
    if test_type == "unit":
        src_path = Path(repo_root) / "tests" / "unit" / source
    else:
        src_path = Path(repo_root) / "tests" / "integration" / source
    
    # Destination paths
    if service == "shared":
        dest_path = Path(repo_root) / "tests" / "shared" / source
    else:
        dest_path = (
            Path(repo_root) / service / "tests" / test_type / source
        )
    
    if not src_path.exists():
        print(f"  ⚠ Source not found: {src_path}")
        return False
    
    # Read, process, and write
    try:
        content = src_path.read_text(encoding='utf-8')
        content = simplify_sys_path(content, service)
        content = update_imports(content, service)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(content, encoding='utf-8')
        print(f"  ✓ Moved {source} to {service}/tests/{test_type}")
        return True
    except Exception as e:
        print(f"  ✗ Error moving {source}: {e}")
        return False


def main():
    repo_root = Path(__file__).parent.parent
    
    print("🚀 Starting test migration...\n")
    
    moved = 0
    failed = 0
    
    for source, service, test_type in TEST_MOVES:
        if move_test_file(str(repo_root), source, service, test_type):
            moved += 1
        else:
            failed += 1
    
    print(f"\n✅ Moved {moved} test files")
    if failed > 0:
        print(f"⚠ Failed to move {failed} test files")
    
    print("\n📝 Next steps:")
    print("  1. Create service-level conftest.py files")
    print("  2. Create pytest.ini files in each service")
    print("  3. Test each service: cd <service> && pytest tests")
    print("  4. Update CI/CD in .github/workflows/ci.yml")
    print("  5. Delete old tests/ directory once verified")


if __name__ == "__main__":
    main()
