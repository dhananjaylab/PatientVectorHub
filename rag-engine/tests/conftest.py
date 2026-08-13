"""
Pytest fixtures for rag-engine service tests.

Provides shared fixtures for RAG engine tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def mock_vector_store():
    """Mock vector store for retrieval tests."""
    store = MagicMock()
    store.search = AsyncMock(
        return_value=[
            MagicMock(
                doc_id="d-001",
                chunk_text="Patient HbA1c 8.4% elevated — type 2 DM.",
                score=0.95,
                document_type="lab_result",
            ),
            MagicMock(
                doc_id="d-002",
                chunk_text="Prescribed metformin 1000mg twice daily.",
                score=0.88,
                document_type="prescription",
            ),
        ]
    )
    return store


@pytest.fixture
def mock_llm():
    """Fake LLM router returning a canned answer."""
    llm = MagicMock()
    llm.complete = AsyncMock(
        return_value=(
            "Based on the retrieved records, the patient shows elevated "
            "HbA1c at 8.4% [1], consistent with type 2 diabetes management. "
            "Metformin 1000mg prescribed [2]."
        )
    )
    return llm


@pytest.fixture
def mock_embeddings_client():
    """Mock embeddings client."""
    client = MagicMock()
    client.embed_query = AsyncMock(
        return_value=[0.1, 0.2, 0.3] * 256  # 768 dims
    )
    return client
