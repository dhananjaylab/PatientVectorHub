#!/usr/bin/env python3
"""Copy vector-store tests and remove sys.path manipulation."""

import re
from pathlib import Path

REPO_ROOT = Path("a:/PatientVectorHub").as_posix().replace("a:/", "a:\\")
REPO_ROOT = Path(REPO_ROOT)

UNIT_TESTS = [
    "test_qdrant_store.py",
    "test_vector_store_factory.py",
    "test_weaviate_schema.py",
    "test_weaviate_search_delete.py",
]

INTEGRATION_TESTS = [
    "test_dual_write_store.py",
    "test_vector_store_layer.py",
]


def clean_sys_path(content: str) -> str:
    """Remove sys.path.insert lines and related imports."""
    lines = content.split('\n')
    new_lines = []
    skip_next_blank_lines = False
    
    for i, line in enumerate(lines):
        # Skip sys.path.insert lines
        if 'sys.path.insert' in line:
            skip_next_blank_lines = True
            continue
        
        # Skip "import sys" or "import os" if they're only used for sys.path
        if (line.strip().startswith('import sys') or line.strip().startswith('import os')):
            # Check if next non-empty line is sys.path.insert
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and 'sys.path.insert' in lines[j]:
                continue
        
        # Skip multiple blank lines after sys.path removal
        if skip_next_blank_lines and line.strip() == '':
            continue
        else:
            skip_next_blank_lines = False
        
        new_lines.append(line)
    
    result = '\n'.join(new_lines)
    
    # Clean up multiple blank lines
    while '\n\n\n' in result:
        result = result.replace('\n\n\n', '\n\n')
    
    return result


def copy_test_file(test_name: str, test_type: str) -> bool:
    """Copy and update a test file."""
    if test_type == 'unit':
        src = REPO_ROOT / 'tests' / 'unit' / test_name
        dst = REPO_ROOT / 'vector-store' / 'tests' / 'unit' / test_name
    else:
        src = REPO_ROOT / 'tests' / 'integration' / test_name
        dst = REPO_ROOT / 'vector-store' / 'tests' / 'integration' / test_name
    
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
    print("Copying vector-store tests...\n")
    
    # Ensure directories exist
    (REPO_ROOT / 'vector-store' / 'tests' / 'unit').mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / 'vector-store' / 'tests' / 'integration').mkdir(parents=True, exist_ok=True)
    
    print("Unit tests:")
    unit_ok = sum(copy_test_file(t, 'unit') for t in UNIT_TESTS)
    
    print(f"\nIntegration tests:")
    int_ok = sum(copy_test_file(t, 'integration') for t in INTEGRATION_TESTS)
    
    total = unit_ok + int_ok
    print(f"\n✅ Copied {total}/{len(UNIT_TESTS) + len(INTEGRATION_TESTS)} tests")


if __name__ == "__main__":
    main()
