"""
Pytest fixtures for ingestion service tests.

Provides shared fixtures for ingestion tests.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def mock_embeddings_client():
    """Mock OpenAI embeddings client."""
    client = MagicMock()
    client.embeddings.create = MagicMock(
        return_value=MagicMock(
            data=[
                MagicMock(embedding=[0.1, 0.2, 0.3] * 256)  # 768 dims
                for _ in range(5)
            ]
        )
    )
    return client


@pytest.fixture
def mock_kafka():
    """Mock Kafka producer."""
    kafka = AsyncMock()
    kafka.send_and_wait = AsyncMock(return_value=None)
    return kafka


@pytest.fixture
def mock_db_session():
    """Mock SQLAlchemy session."""
    session = MagicMock()
    session.execute = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session
