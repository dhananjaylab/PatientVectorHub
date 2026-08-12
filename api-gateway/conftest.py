"""
conftest.py for api-gateway service tests.

This file allows pytest to discover tests in the api-gateway/tests directory.
It delegates to tests/conftest.py for actual fixture definitions.
"""

import sys
import os

# Add api-gateway/src to path so tests can import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Import shared fixtures from tests/conftest
import pytest
pytest_plugins = ["tests.conftest"]
