"""
Pytest fixtures for vector-store service tests.

Provides shared fixtures for vector store tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def mock_weaviate():
    """Fake WeaviateStore returning deterministic search results."""
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            MagicMock(
                doc_id="d-001",
                chunk_text="Patient HbA1c 8.4% elevated — type 2 DM.",
                score=0.95,
                document_type="lab_result",
                metadata={},
            ),
            MagicMock(
                doc_id="d-002",
                chunk_text="Prescribed metformin 1000mg twice daily.",
                score=0.88,
                document_type="prescription",
                metadata={},
            ),
        ]
    )
    store.upsert = AsyncMock(return_value=None)
    store.delete = AsyncMock(return_value=None)
    store.health_check = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_qdrant():
    """Fake QdrantStore."""
    store = MagicMock()
    store.search = AsyncMock(return_value=[])
    store.upsert = AsyncMock(return_value=None)
    store.delete = AsyncMock(return_value=None)
    store.health_check = AsyncMock(return_value=True)
    return store
