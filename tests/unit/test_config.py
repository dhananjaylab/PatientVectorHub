"""Unit tests for Settings / configuration loading."""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))


def test_settings_singleton():
    from src.config import settings as s1
    from src.config import settings as s2
    assert s1 is s2


def test_database_url_contains_pvh():
    from src.config import settings
    assert "pvh" in settings.DATABASE_URL


def test_vault_addr_is_http():
    from src.config import settings
    assert settings.VAULT_ADDR.startswith("http")


def test_vector_backend_default():
    from src.config import settings
    assert settings.VECTOR_BACKEND in ("weaviate", "qdrant")


def test_cors_origins_list_is_list():
    from src.config import settings
    result = settings.cors_origins_list
    assert isinstance(result, list)
    assert all(o.startswith("http") for o in result)


def test_llm_max_tokens_positive():
    from src.config import settings
    assert settings.LLM_MAX_TOKENS > 0


def test_api_port_valid():
    from src.config import settings
    assert 1024 <= settings.API_PORT <= 65535


def test_vector_cloud_settings():
    from src.config import settings
    assert hasattr(settings, "WEAVIATE_URL")
    assert hasattr(settings, "WEAVIATE_API_KEY")
    assert hasattr(settings, "QDRANT_URL")
    assert hasattr(settings, "QDRANT_API_KEY")

