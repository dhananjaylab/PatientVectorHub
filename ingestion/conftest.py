"""
conftest.py for ingestion service tests.

FIX (test-structure sign-off round): same class of bug as
`rag-engine/conftest.py` and `api-gateway/conftest.py` — this file
previously made no attempt to alias `vector_store` at all, even though
`ingestion/src/workers/batch_worker.py` cross-imports it the same way
`rag-engine/src/retriever.py` does. Not yet triggered by an existing
failing test (no current `ingestion/tests/` file imports
`batch_worker.py` directly), but fixed now for consistency and so the
next test that needs it doesn't rediscover the same gap. Also removed
the redundant `sys.path.insert(0, .../src)` — see
`rag-engine/conftest.py`'s docstring for why that's not just harmless
but actively risky for modules using internal relative imports.
"""

import importlib.util
import os
import sys


def _ensure_cross_package_alias(target_src_dir: str, module_name: str) -> None:
    if module_name in sys.modules:
        return
    init_path = os.path.join(target_src_dir, "__init__.py")
    if not os.path.isfile(init_path):
        return
    spec = importlib.util.spec_from_file_location(
        module_name, init_path, submodule_search_locations=[target_src_dir]
    )
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


_here = os.path.dirname(os.path.abspath(__file__))
_ensure_cross_package_alias(os.path.join(_here, "..", "vector-store", "src"), "vector_store")
