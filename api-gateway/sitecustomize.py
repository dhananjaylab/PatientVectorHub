"""Ensure sibling service modules are importable during local development.

This project keeps rag-engine and vector-store as sibling directories rather than
installing them as editable packages in the API gateway virtualenv. When the API
Gateway is started directly from its own folder, Python does not automatically add
those sibling src directories to sys.path.

By placing this module in the API gateway root, Python imports it automatically on
startup and adds the required project-local source trees for cross-service imports
such as `from rag_engine.config import settings`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRA_PATHS = [
    ROOT / "rag-engine" / "src",
    ROOT / "vector-store" / "src",
]

for path in EXTRA_PATHS:
    resolved = str(path)
    if path.exists() and resolved not in sys.path:
        sys.path.insert(0, resolved)
