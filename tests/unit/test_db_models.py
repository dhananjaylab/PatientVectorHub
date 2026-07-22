"""Unit tests for api-gateway/src/db/models.py — no DB connection required."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "api-gateway"))


class TestModelsImport:
    def test_models_module_imports(self):
        from src.db import models
        assert models.Base is not None

    def test_all_eight_tables_present(self):
        from src.db.models import Base
        table_names = set(Base.metadata.tables.keys())
        assert table_names == {
            "tenants", "users", "patients", "ingestion_jobs",
            "documents", "api_keys", "audit_logs", "query_logs",
        }


class TestTenantScopedTables:
    """Every table except tenants itself must carry a tenant_id column —
    that's the precondition for migration 003/004's RLS policies to even
    make sense. This test exists so a future model addition that forgets
    tenant_id fails loudly here instead of silently shipping without RLS.
    """

    def test_non_root_tables_have_tenant_id(self):
        from src.db.models import Base
        for name, table in Base.metadata.tables.items():
            if name == "tenants":
                continue
            assert "tenant_id" in table.columns, f"{name} is missing tenant_id"

    def test_tenants_table_has_no_tenant_id(self):
        from src.db.models import Base
        assert "tenant_id" not in Base.metadata.tables["tenants"].columns


class TestForeignKeys:
    def test_documents_references_patients_and_ingestion_jobs(self):
        from src.db.models import Base
        fk_targets = {
            fk.target_fullname for fk in Base.metadata.tables["documents"].foreign_keys
        }
        assert "patients.id" in fk_targets
        assert "ingestion_jobs.id" in fk_targets
        assert "tenants.id" in fk_targets

    def test_api_keys_references_users_and_tenants(self):
        from src.db.models import Base
        fk_targets = {
            fk.target_fullname for fk in Base.metadata.tables["api_keys"].foreign_keys
        }
        assert "users.id" in fk_targets
        assert "tenants.id" in fk_targets

    def test_audit_logs_patient_id_is_not_a_foreign_key(self):
        # Deliberate: patient_id on audit_logs is a plain uuid, not an FK,
        # so audit rows can outlive a deleted/anonymized patient record.
        from src.db.models import Base
        columns_with_fks = {
            col.name for col in Base.metadata.tables["audit_logs"].columns if col.foreign_keys
        }
        assert "patient_id" not in columns_with_fks


class TestAuditLogMetadataColumnMapping:
    def test_metadata_attribute_maps_to_metadata_db_column(self):
        # `metadata` is reserved on the declarative Base itself (the schema
        # registry object), so the ORM attribute here is named
        # audit_metadata but must map to the actual `metadata` column doc
        # 05's schema specifies. Checked at the Table level (unambiguous)
        # rather than via attribute-proxy behavior on the class.
        from src.db.models import AuditLog
        assert "metadata" in AuditLog.__table__.columns
        assert hasattr(AuditLog, "audit_metadata")
