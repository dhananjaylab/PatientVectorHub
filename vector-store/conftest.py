"""
conftest.py for vector-store service tests.

This file allows pytest to discover tests in the vector-store/tests directory.
"""

import sys
import os

# Add vector-store/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Add parent directory (PatientVectorHub) to path so scripts can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Add vector-store directory itself to path so its own scripts take precedence
sys.path.insert(0, os.path.dirname(__file__))

