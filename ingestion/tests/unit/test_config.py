"""Unit tests for Settings / configuration loading."""
import sys
import os
import pytest

def test_settings_singleton():
    from src.config import settings as s1
    from src.config import settings as s2
    assert s1 is s2

def test_database_url_contains_pvh():
    from src.config import settings
    assert "pvh" in settings.DATABASE_URL or "defaultdb" in settings.DATABASE_URL

def test_vault_addr_is_http():
    from src.config import settings
    assert settings.VAULT_ADDR.startswith("http")

def test_vector_backend_default():
    from src.config import settings
    assert settings.VECTOR_BACKEND in ("weaviate", "qdrant")

def test_embedding_provider_is_valid():
    """Test that EMBEDDING_PROVIDER is set to a valid value."""
    from src.config import settings
    assert settings.EMBEDDING_PROVIDER in ("openai", "clinical_bert")

def test_embedding_dimensions_positive():
    """Test that EMBEDDING_DIMENSIONS is a positive integer."""
    from src.config import settings
    assert settings.EMBEDDING_DIMENSIONS > 0

def test_kafka_brokers_configured():
    """Test that Kafka brokers are configured."""
    from src.config import settings
    assert len(settings.KAFKA_BROKERS) > 0

def test_vector_cloud_settings():
    from src.config import settings
    assert hasattr(settings, "WEAVIATE_URL")
    assert hasattr(settings, "WEAVIATE_API_KEY")
    assert hasattr(settings, "QDRANT_URL")
    assert hasattr(settings, "QDRANT_API_KEY")

