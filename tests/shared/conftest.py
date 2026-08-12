"""
Pytest fixtures for cross-service integration tests (shared).

These tests require multiple services to be running.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop_policy():
    """Event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def mock_postgres_url():
    """Mock PostgreSQL connection URL."""
    return "postgresql://user:pass@localhost/pvh_test"


@pytest.fixture
def mock_kafka_brokers():
    """Mock Kafka broker list."""
    return ["localhost:9092"]


@pytest.fixture
def mock_vault_url():
    """Mock Vault server URL."""
    return "http://localhost:8200"
