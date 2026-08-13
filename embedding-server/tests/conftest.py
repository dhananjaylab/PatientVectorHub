"""
Pytest fixtures for embedding-server tests.

Provides shared fixtures for embedding server tests.
"""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_model():
    """Mock HuggingFace model."""
    model = MagicMock()
    model.encode = MagicMock(
        return_value=[[0.1, 0.2, 0.3] * 256]  # 768 dims
    )
    return model
