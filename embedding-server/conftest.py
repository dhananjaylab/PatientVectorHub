"""
conftest.py for embedding-server tests.

This file allows pytest to discover tests in the embedding-server/tests directory.
"""

import sys
import os

# Add embedding-server/src to path if it exists
src_path = os.path.join(os.path.dirname(__file__), "src")
if os.path.isdir(src_path):
    sys.path.insert(0, src_path)
