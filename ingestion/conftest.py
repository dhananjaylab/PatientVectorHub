"""
conftest.py for ingestion service tests.

This file allows pytest to discover tests in the ingestion/tests directory.
"""

import sys
import os

# Add ingestion/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
