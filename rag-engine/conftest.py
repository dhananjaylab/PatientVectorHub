"""
conftest.py for rag-engine service tests.

This file allows pytest to discover tests in the rag-engine/tests directory.

FIX (test-structure sign-off round): `rag-engine/pytest.ini`'s `pythonpath = .`
already makes `src` (this directory's `src/`) a properly importable package —
that's what makes `from src import retriever` work in the test files, since
`src/__init__.py` exists and `rag-engine/` itself is on the path. The
`sys.path.insert(0, .../src)` line this file previously had was redundant
with that (and risked registering rag-engine's modules under two different
identities — `src.retriever` via pytest.ini, and a bare top-level `retriever`
via this insert — which would have broken any module using an internal
relative import like `from .config import settings`, since a module loaded
without a parent package can't resolve those). Removed rather than kept
"just in case" — it wasn't doing anything the pytest.ini setting doesn't
already do correctly.

The `vector_store` handling was the real, verified-broken bug:
`sys.path.insert(0, ".../vector-store/src")` puts that directory's *files*
directly on the path as bare top-level modules (`interface.py` becomes
importable as bare `import interface`), not as a package literally named
`vector_store` — which is what `retriever.py`/`synthesizer.py`'s
`from vector_store.interface import ...` actually needs. Confirmed by
reproducing it directly: that exact setup raises
`ModuleNotFoundError: No module named 'vector_store'`. Fixed the same way
the original root `tests/conftest.py` fixed it (see
`_ensure_cross_package_alias()` there) — via `importlib.util.
spec_from_file_location()`, which properly registers `vector-store/src` as
the top-level `vector_store` package rather than dumping its contents flat
onto the path.
"""

import importlib.util
import os
import sys


def _ensure_cross_package_alias(target_src_dir: str, module_name: str) -> None:
    """Make target_src_dir importable as the top-level `module_name`
    package. See this file's module docstring for why a plain
    sys.path.insert(0, target_src_dir) is not equivalent."""
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
