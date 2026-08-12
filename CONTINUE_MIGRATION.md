# Continue Migration — Ingestion, Vector Store, RAG Engine, Embedding Server

You've successfully migrated API Gateway tests. Here's how to continue with other services.

## Quick Status
- ✅ **API Gateway**: 56 tests passing
- ⏳ **Ingestion**: Ready to migrate
- ⏳ **Vector Store**: Ready to migrate
- ⏳ **RAG Engine**: Ready to migrate
- ⏳ **Embedding Server**: Ready to migrate

## One-Line Quick Start Per Service

```bash
# Ingestion
cd ingestion && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && pytest tests

# Vector Store
cd vector-store && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && pytest tests

# RAG Engine
cd rag-engine && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && pytest tests

# Embedding Server
cd embedding-server && python -m venv venv && source venv/bin/activate && pip install -r requirements.txt && pytest tests
```

## Step-by-Step for Each Service

### 1. Create Python Migration Script for Service

```python
# scripts/copy_and_update_<service>_tests.py
# Copy template from: scripts/copy_and_update_api_gateway_tests.py
# Update UNIT_TESTS and INTEGRATION_TESTS lists for the service
```

### 2. Run Migration

```bash
cd /repo/root
python scripts/copy_and_update_<service>_tests.py
```

### 3. Test It

```bash
cd <service>
pytest tests -q     # Quick test
pytest tests -v     # Verbose test
```

### 4. Fix Any Failures

Most will be import-related. Check which modules the service needs and update imports.

## Detailed Steps for Each Service

### Ingestion Service

**Tests to migrate** (9 total):

Unit tests (7):
- test_config.py
- test_embeddings_provider_routing.py
- test_ingestion_chunker.py
- test_ingestion_dlq.py
- test_ingestion_embedder.py
- test_ingestion_parsers.py
- test_llm_router.py

Integration tests (2):
- test_ingestion_dlq_end_to_end.py
- test_ingestion_end_to_end.py

**Steps:**
```bash
# 1. Create migration script
cat > scripts/copy_and_update_ingestion_tests.py << 'EOF'
#!/usr/bin/env python3
import re
from pathlib import Path

REPO_ROOT = Path("a:/PatientVectorHub").as_posix().replace("a:/", "a:\\")
REPO_ROOT = Path(REPO_ROOT)

UNIT_TESTS = [
    "test_config.py",
    "test_embeddings_provider_routing.py",
    "test_ingestion_chunker.py",
    "test_ingestion_dlq.py",
    "test_ingestion_embedder.py",
    "test_ingestion_parsers.py",
    "test_llm_router.py",
]

INTEGRATION_TESTS = [
    "test_ingestion_dlq_end_to_end.py",
    "test_ingestion_end_to_end.py",
]

def clean_sys_path(content: str) -> str:
    """Remove sys.path.insert lines and related imports."""
    lines = content.split('\n')
    new_lines = []
    skip_next_blank_lines = False
    
    for i, line in enumerate(lines):
        if 'sys.path.insert' in line:
            skip_next_blank_lines = True
            continue
        if (line.strip().startswith('import sys') or line.strip().startswith('import os')):
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and 'sys.path.insert' in lines[j]:
                continue
        if skip_next_blank_lines and line.strip() == '':
            continue
        else:
            skip_next_blank_lines = False
        new_lines.append(line)
    
    result = '\n'.join(new_lines)
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    return result

def copy_test_file(test_name: str, test_type: str) -> bool:
    if test_type == 'unit':
        src = REPO_ROOT / 'tests' / 'unit' / test_name
        dst = REPO_ROOT / 'ingestion' / 'tests' / 'unit' / test_name
    else:
        src = REPO_ROOT / 'tests' / 'integration' / test_name
        dst = REPO_ROOT / 'ingestion' / 'tests' / 'integration' / test_name
    
    if not src.exists():
        print(f"  ⚠ {test_name}: source not found")
        return False
    
    try:
        content = src.read_text(encoding='utf-8')
        content = clean_sys_path(content)
        dst.write_text(content, encoding='utf-8')
        print(f"  ✓ {test_name}")
        return True
    except Exception as e:
        print(f"  ✗ {test_name}: {e}")
        return False

def main():
    print("Copying ingestion tests...\n")
    
    (REPO_ROOT / 'ingestion' / 'tests' / 'unit').mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / 'ingestion' / 'tests' / 'integration').mkdir(parents=True, exist_ok=True)
    
    print("Unit tests:")
    unit_ok = sum(copy_test_file(t, 'unit') for t in UNIT_TESTS)
    
    print(f"\nIntegration tests:")
    int_ok = sum(copy_test_file(t, 'integration') for t in INTEGRATION_TESTS)
    
    total = unit_ok + int_ok
    print(f"\n✅ Copied {total}/{len(UNIT_TESTS) + len(INTEGRATION_TESTS)} tests")

if __name__ == "__main__":
    main()
EOF

# 2. Run migration
python scripts/copy_and_update_ingestion_tests.py

# 3. Setup venv and test
cd ingestion
python -m venv venv
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate      # Windows
pip install -r requirements.txt
pytest tests -q
```

### Vector Store Service

**Tests to migrate** (6 total):

Unit tests (4):
- test_qdrant_store.py
- test_vector_store_factory.py
- test_weaviate_schema.py
- test_weaviate_search_delete.py

Integration tests (2):
- test_dual_write_store.py
- test_vector_store_layer.py

```bash
# Same pattern as ingestion — create migration script, run it, test
cd vector-store
pytest tests -q
```

### RAG Engine Service

**Tests to migrate** (4 total):

Unit tests (3):
- test_query_embedder.py
- test_rag_synthesizer.py
- test_retriever.py

Integration tests (1):
- test_rag_query_pipeline.py

### Embedding Server Service

**Tests to migrate** (3 total):

Unit tests (3):
- test_clinical_bert_embedder.py
- test_hf_deploy_script.py
- test_logging.py

## Template Script

All migration scripts follow this pattern. Update the lists and service name:

```python
UNIT_TESTS = [
    "test_file1.py",
    "test_file2.py",
    # ... etc
]

INTEGRATION_TESTS = [
    "test_integration1.py",
    # ... etc
]
```

## Expected Results

After migration, each service should show test collection and execution:

```
===== test session starts =====
collected XX items

tests/unit/... PASSED [100%]
===== XX passed in Xs =====
```

## Common Issues & Fixes

### Issue: `ModuleNotFoundError: No module named 'xyz'`
**Fix:** Install that module's requirements or mock it in tests/conftest.py

### Issue: `Import error from 'src'`
**Fix:** Ensure the service's `conftest.py` is in place and pytest.ini has `pythonpath = .`

### Issue: Tests run but have failures
**Fix:** This is OK for now. Service-specific tests often require live services (DB, Redis, etc.). Focus on tests that pass locally.

## Batch Migration (All Services)

To migrate all services quickly:

```bash
cd /repo/root

# Create all migration scripts
for service in ingestion vector-store rag-engine embedding-server; do
    python scripts/copy_and_update_${service}_tests.py
done

# Test each service
for service in ingestion vector-store rag-engine embedding-server; do
    cd $service
    pytest tests -q
    cd ..
done
```

## After Migration

Once all services are migrated:

1. **Update each service's README** with test instructions
2. **Update CI/CD** (.github/workflows/ci.yml) to run per-service tests in parallel
3. **Archive old tests/** directory (keep as backup reference)
4. **Create integration test suite** in tests/shared/

## Progress Tracking

| Service | Status | Unit | Integration | Notes |
|---------|--------|------|-------------|-------|
| api-gateway | ✅ Done | 6 ✓ | 3 | 56 passing |
| ingestion | ⏳ Ready | 7 | 2 | Ready to migrate |
| vector-store | ⏳ Ready | 4 | 2 | Ready to migrate |
| rag-engine | ⏳ Ready | 3 | 1 | Ready to migrate |
| embedding-server | ⏳ Ready | 3 | 0 | Ready to migrate |

## Questions?

- See **TESTING.md** for complete testing guide
- See **TESTING_QUICK_START.md** for quick reference
- See **TEST_STRUCTURE_REFERENCE.txt** for command reference
- See **scripts/** for existing migration scripts

---

**Next Action:** Choose a service and run its migration script!

Recommended order: ingestion → vector-store → rag-engine → embedding-server
