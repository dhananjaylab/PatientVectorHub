"""
conftest.py for rag-engine service tests.

This file allows pytest to discover tests in the rag-engine/tests directory.
"""

import sys
import os

# Add rag-engine/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Make vector_store available as cross-package import
_vector_store_path = os.path.join(os.path.dirname(__file__), "..", "vector-store", "src")
if os.path.isdir(_vector_store_path):
    sys.path.insert(0, _vector_store_path)
