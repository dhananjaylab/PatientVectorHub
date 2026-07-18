import unittest

from weaviate.classes.config import Configure, VectorDistances

from scripts.setup_weaviate_schema import (
    COLLECTION_NAME,
    build_vector_index_config,
)


class WeaviateSchemaTestCase(unittest.TestCase):
    def test_collection_name_is_shared(self) -> None:
        """The collection name must be the single shared constant, not per-tenant."""
        self.assertEqual(COLLECTION_NAME, "PatientDocument")

    def test_build_vector_index_config_uses_hfresh_for_cloud(self) -> None:
        """Weaviate Cloud only allows hfresh; verify the cloud path returns it."""
        config = build_vector_index_config(
            use_cloud=True,
            configure_module=Configure,
            vector_distances=VectorDistances,
        )
        self.assertEqual(type(config).__name__, "_VectorIndexConfigHFreshCreate")

    def test_build_vector_index_config_uses_hnsw_for_local(self) -> None:
        """Self-hosted path must use standard HNSW with explicit tuning params."""
        config = build_vector_index_config(
            use_cloud=False,
            configure_module=Configure,
            vector_distances=VectorDistances,
        )
        self.assertEqual(type(config).__name__, "_VectorIndexConfigHNSWCreate")


if __name__ == "__main__":
    unittest.main()
