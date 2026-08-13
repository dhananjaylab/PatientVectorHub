"""
conftest.py for api-gateway service tests.

This file allows pytest to discover tests in the api-gateway/tests directory.
It delegates to tests/conftest.py for actual fixture definitions.

FIX (test-structure sign-off round): this file previously did not attempt to
make `rag_engine` or `vector_store` resolvable at all — `pytest.ini`'s
`pythonpath = .` only adds `api-gateway/` itself. `routers/query.py` imports
`rag_engine.retriever` and `rag_engine.synthesizer` directly (which
themselves import `vector_store.interface`), so
`tests/unit/test_query_router.py` failed to collect entirely
(`ModuleNotFoundError: No module named 'rag_engine'`), confirmed by
reproducing it directly. Same root cause and same fix as
`rag-engine/conftest.py` — see that file's docstring for the full
reasoning on why `importlib.util.spec_from_file_location()` is needed
here rather than a plain `sys.path.insert()`.

Also removed the redundant `sys.path.insert(0, .../src)` this file
previously had — `pytest.ini`'s `pythonpath = .` already makes `src` a
properly importable package (that's what `from src.routers.query import
router` relies on), and the extra insert risked double-registering
api-gateway's own modules under two identities the same way it would
have for rag-engine (see that file's docstring for the specific relative-
import breakage that risks).

Also removed `pytest_plugins = ["tests.conftest"]` — pytest already
auto-discovers `tests/conftest.py` on its own (it's inside `testpaths`),
and declaring it as a plugin too caused a real, reproduced crash:
`ValueError: Plugin already registered under a different name`, since
pytest ended up trying to register the same module under two identities
at once. This broke collection for every test in this service, not just
the ones that needed the shared fixtures.
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
    try:
        spec.loader.exec_module(module)
    except ImportError as e:
        # If cross-package dependencies are missing, register a placeholder
        # module so tests that don't need these packages can still run
        import warnings
        warnings.warn(
            f"Could not import {module_name}: {e}. "
            f"Tests requiring {module_name} will fail.",
            ImportWarning
        )
        # Keep the empty module registered to avoid repeated import attempts
        pass


_here = os.path.dirname(os.path.abspath(__file__))
_ensure_cross_package_alias(os.path.join(_here, "..", "rag-engine", "src"), "rag_engine")
_ensure_cross_package_alias(os.path.join(_here, "..", "vector-store", "src"), "vector_store")

# NOTE: no `pytest_plugins = ["tests.conftest"]` here — pytest already
# auto-discovers `tests/conftest.py` on its own via normal conftest
# collection (it's inside `testpaths`), and explicitly declaring it as a
# plugin too causes pytest to try to register the same module under two
# different names: `ValueError: Plugin already registered under a
# different name: .../tests/conftest.py=<module 'tests.conftest' ...>`.
# Confirmed by reproducing it directly — this crashed collection for
# every test in this service, not just the ones that needed it.
