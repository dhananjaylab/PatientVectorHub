#!/usr/bin/env python3
"""
Seed synthetic test data - NO real PHI.
Creates: 2 tenants, 4 users per tenant (one per role), 1000 patients per
tenant, plus (Phase 2 addition) 1 sample ingestion_jobs row, 3 sample
documents, and 1 sample api_keys row per tenant so the tables added in
migration 004 aren't empty when exercising CRUD/tests locally.
Safe to run multiple times (ON CONFLICT DO NOTHING / explicit reset).

RLS note (migration 003_enable_rls.py, extended by 004_add_core_tables.py)
---------------------------------------------------------------------------
`users`, `patients`, `ingestion_jobs`, `documents`, and `api_keys` all run
under FORCE ROW LEVEL SECURITY with a policy requiring
tenant_id = current_setting('app.tenant_id')::uuid on every INSERT (via
WITH CHECK) and SELECT/UPDATE/DELETE (via USING).

This script therefore calls _set_tenant_context() before every batch of
inserts into those tables, scoping the connection's session GUC to the
tenant being seeded.

Locally, against the docker-compose Postgres, this was invisible before
this patch: POSTGRES_USER=pvh is bootstrapped as a Postgres superuser by
the official postgres image's initdb step, and superusers always bypass
RLS regardless of FORCE. Without _set_tenant_context(), this exact same
script fails on Aiven (and any other managed Postgres where the app role
is not a superuser) with:
    psycopg2.errors.InsufficientPrivilege: new row violates row-level
    security policy for table "users" / "patients"
"""
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import base64
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Connection
except ImportError:
    create_engine = None
    text = None
    Connection = None

try:
    import hvac
except ImportError:
    hvac = None

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# ── Vault Transit PHI encryption (Phase 10 / ADR-017) ───────────────────────
# Same defensive-import posture this file already uses for sqlalchemy
# above (degrade gracefully rather than hard-crash on an optional dep) —
# hvac not being installed in whatever environment runs this script
# falls back to fake_mrn() below, same as sqlalchemy missing already
# printed a message and exited rather than raising an ImportError
# traceback.
VAULT_ADDR = os.getenv("VAULT_ADDR", "http://localhost:8200")
VAULT_TOKEN = os.getenv("VAULT_TOKEN", "dev-root-token")
VAULT_TRANSIT_KEY = os.getenv("VAULT_TRANSIT_KEY", "phi-key")
# Mirrors ingestion/src/config.py's and api-gateway/src/config.py's own
# ALLOW_REAL_PHI guardrail — same name, same default, so one env var
# means the same thing everywhere. This script has always generated
# only synthetic data (see module docstring: "NO real PHI") regardless
# of this flag; what ALLOW_REAL_PHI controls here is specifically
# whether a Vault-unreachable seed run is allowed to silently fall back
# to a placeholder MRN shape, or must fail loudly instead — see
# resolve_mrn() below.
ALLOW_REAL_PHI = os.getenv("ALLOW_REAL_PHI", "false").lower() == "true"

_vault_client = None


def _get_vault_client():
    global _vault_client
    if _vault_client is None and hvac is not None:
        _vault_client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
    return _vault_client


def _vault_ready() -> bool:
    """Checked ONCE per seed() run, not once per patient (2000 health +
    read_key calls before every one of 2000 encrypts would be wasteful
    -- see resolve_mrn()'s caller in seed() for how the result is
    threaded through instead of re-checked)."""
    if hvac is None:
        return False
    client = _get_vault_client()
    try:
        client.sys.read_health_status(method="GET")
        client.secrets.transit.read_key(name=VAULT_TRANSIT_KEY)
        return True
    except Exception:
        return False


def _mrn_plaintext_for_seed(seed: str) -> str:
    """The synthetic (never-real) value that gets encrypted -- same
    deterministic per-seed shape the old fake_mrn() always used, minus
    the "vault:v1:SEED_" wrapping (that wrapping is now genuinely
    Vault's own ciphertext format, not something to hand-roll)."""
    h = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    return f"SEED-MRN-{h}"


def real_mrn(seed: str) -> str:
    """Encrypts synthetic plaintext via a REAL Vault Transit call --
    proves this phase's actual encryption pathway end to end (same
    api-gateway/src/vault_client.py encrypt_phi_sync() logic, verified
    against an actually-installed hvac the same way there) rather than
    a hand-rolled lookalike string. The plaintext being encrypted is
    still synthetic (_mrn_plaintext_for_seed) -- only the ENCRYPTION is
    real, which is the part this phase actually needed to prove works.
    """
    client = _get_vault_client()
    plaintext = _mrn_plaintext_for_seed(seed)
    b64_plaintext = base64.b64encode(plaintext.encode("utf-8")).decode("ascii")
    response = client.secrets.transit.encrypt_data(
        name=VAULT_TRANSIT_KEY, plaintext=b64_plaintext
    )
    return response["data"]["ciphertext"]


def fake_mrn(seed: str) -> str:
    """Fallback placeholder when Vault isn't reachable/configured --
    kept in the same "vault:v1:..."-shaped format Vault's own ciphertext
    uses, so patients.mrn never has two visually different value shapes
    depending on which environment seeded a given row. Used only when
    ALLOW_REAL_PHI is NOT set -- see resolve_mrn()."""
    h = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    return f"vault:v1:SEED_{h}"


def resolve_mrn(seed: str, *, vault_ready: bool) -> str:
    """Real encryption when Vault is actually reachable; a clearly
    fake-shaped placeholder when it isn't AND real PHI was never in
    play (ALLOW_REAL_PHI unset — the common case for casual local dev
    without `docker-compose up vault`); fail-closed (raise, don't seed
    at all) when ALLOW_REAL_PHI is set and Vault genuinely isn't
    available — mirrors vault_client.py's require_vault_or_fail_closed()
    for exactly the same reason: an environment that's supposed to
    handle real PHI must never silently persist anything unencrypted,
    not even in a seed script most people think of as "just test data".
    """
    if vault_ready:
        return real_mrn(seed)
    if ALLOW_REAL_PHI:
        raise RuntimeError(
            "ALLOW_REAL_PHI is set but Vault is unreachable at "
            f"{VAULT_ADDR} or transit key '{VAULT_TRANSIT_KEY}' doesn't "
            "exist -- refusing to seed PHI-shaped data unencrypted. Run "
            "infra/scripts/vault_init.sh first, or start Vault via "
            "`docker-compose up vault`."
        )
    return fake_mrn(seed)


def get_database_url() -> str:
    """Return a sync SQLAlchemy URL suitable for psycopg2."""
    url = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC or DATABASE_URL must be set in .env")

    url = url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))

    # Aiven requires SSL; psycopg2 expects sslmode in the URL query string.
    if "aivencloud.com" in (parts.hostname or ""):
        query.setdefault("sslmode", "require")

    query.setdefault("connect_timeout", "10")
    query.setdefault("options", "-c statement_timeout=30000")

    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

TENANT_A = "00000000-0000-0000-0000-000000000001"
TENANT_B = "00000000-0000-0000-0000-000000000002"

TENANTS = [
    {"id": TENANT_A, "name": "Acme Health", "namespace": "ns_acme"},
    {"id": TENANT_B, "name": "Riverside Medical", "namespace": "ns_riverside"},
]

ROLES = ["admin", "engineer", "analyst", "auditor"]

DOCUMENT_TYPES = ["clinical_note", "lab_result", "imaging_report"]


def fake_api_key_hash(seed: str) -> tuple[str, str]:
    """Return (plaintext, sha256_hash) for a deterministic seed API key.
    Plaintext is printed once at the end of the run, same as the real
    create_api_key() flow — never persisted anywhere but the hash."""
    raw = f"pvh_seed_{secrets.token_urlsafe(24)}_{seed}"
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def _set_tenant_context(conn: "Connection", tenant_id: str) -> None:
    """Scope subsequent statements on this connection to tenant_id, to
    satisfy the RLS policies from migration 003_enable_rls.py and
    004_add_core_tables.py.

    Uses set_config(..., is_local=True) rather than a literal
    `SET LOCAL app.tenant_id = '...'` because SET/SET LOCAL do not
    accept bound parameters over the wire protocol -- set_config() is
    the parameterizable equivalent. is_local=True scopes the value to
    the current transaction, so it automatically resets on
    conn.commit() rather than leaking into whatever the pooled
    connection is used for next.

    Required on every environment where the connecting role is not a
    Postgres superuser (e.g. Aiven-managed Postgres, which does not
    grant SUPERUSER to application roles). Local Docker Compose
    Postgres happens to work without this too, because POSTGRES_USER
    is bootstrapped as a superuser there -- but don't rely on that.
    """
    conn.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": tenant_id},
    )


def _reset_seed_data(conn: "Connection") -> None:
    """Remove previously seeded tenant rows so reruns stay deterministic."""
    for tid in [TENANT_A, TENANT_B]:
        _set_tenant_context(conn, tid)
        # Children before parents — documents references ingestion_jobs
        # and patients; api_keys/ingestion_jobs reference users.
        conn.execute(text("DELETE FROM documents WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM api_keys WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM ingestion_jobs WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM patients WHERE tenant_id = :tid"), {"tid": tid})
        conn.execute(text("DELETE FROM users WHERE tenant_id = :tid"), {"tid": tid})

    conn.execute(
        text("DELETE FROM tenants WHERE id IN (:tenant_a, :tenant_b)"),
        {"tenant_a": TENANT_A, "tenant_b": TENANT_B},
    )


def seed() -> None:
    if create_engine is None:
        print("SQLAlchemy not installed - cannot seed")
        sys.exit(1)

    engine = create_engine(get_database_url(), echo=False, pool_pre_ping=True)
    seed_api_keys: list[tuple[str, str]] = []  # (label, plaintext) — printed at the end

    # Phase 10 / ADR-017: checked ONCE here, not once per patient (2000
    # health + read_key calls before every one of 2000 encrypts would be
    # wasteful) -- threaded through to resolve_mrn() below.
    vault_ready = _vault_ready()
    if vault_ready:
        print(f"  OK Vault reachable at {VAULT_ADDR}, transit key '{VAULT_TRANSIT_KEY}' "
              "exists -- patient MRNs will be REAL Vault Transit ciphertext "
              "(encrypting synthetic plaintext, per this script's own "
              "'NO real PHI' data)")
    elif ALLOW_REAL_PHI:
        print(f"  FAIL ALLOW_REAL_PHI=true but Vault is unreachable at {VAULT_ADDR} "
              f"or transit key '{VAULT_TRANSIT_KEY}' is missing.")
        print("  Run infra/scripts/vault_init.sh first, or `docker-compose up vault`.")
        sys.exit(1)
    else:
        print(f"  WARN Vault unreachable at {VAULT_ADDR} -- falling back to fake_mrn() "
              "placeholder ciphertext-shaped strings (fine for casual local dev "
              "without `docker-compose up vault`; will refuse to run this way "
              "once ALLOW_REAL_PHI=true)")

    print("Connecting to configured PostgreSQL database...")
    with engine.connect() as conn:
        print("Connected. Seeding rows...")
        _reset_seed_data(conn)

        # Tenants -- not RLS-scoped (root table, no tenant_id column).
        for t in TENANTS:
            conn.execute(text(
                "INSERT INTO tenants (id, name, namespace, plan, created_at)"
                " VALUES (:id, :name, :ns, 'enterprise', NOW())"
                " ON CONFLICT (id) DO NOTHING"
            ), {"id": t["id"], "name": t["name"], "ns": t["namespace"]})
        print(f"  OK {len(TENANTS)} tenants seeded")

        # Users (one per role per tenant) -- RLS-scoped, set context per tenant.
        user_ids: dict[str, dict[str, str]] = {}  # tenant_id -> {role: user_id}
        user_count = 0
        for i, tid in enumerate([TENANT_A, TENANT_B]):
            tenant_label = f"tenant{i + 1}"
            user_ids[tid] = {}
            _set_tenant_context(conn, tid)
            for role in ROLES:
                uid = str(uuid.uuid5(
                    uuid.NAMESPACE_DNS, f"{role}@{tenant_label}.test"
                ))
                user_ids[tid][role] = uid
                conn.execute(text(
                    "INSERT INTO users"
                    " (id, email, keycloak_subject, role, tenant_id, is_active, created_at)"
                    " VALUES (:id, :email, :ks, :role, :tid, TRUE, NOW())"
                    " ON CONFLICT (keycloak_subject) DO NOTHING"
                ), {
                    "id": uid,
                    "email": f"{role}@{tenant_label}.test",
                    "ks": f"kc-{role}-{tenant_label}",
                    "role": role,
                    "tid": tid,
                })
                user_count += 1
        print(f"  OK {user_count} users seeded ({len(ROLES)} roles x {len(TENANTS)} tenants)")

        # Patients (1000 per tenant) -- RLS-scoped, set context per tenant.
        patient_count = 0
        patient_sample_ids: dict[str, list[str]] = {}
        for tid in [TENANT_A, TENANT_B]:
            _set_tenant_context(conn, tid)
            batch = []
            sample_ids = []
            for j in range(1000):
                pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"patient-{tid}-{j}"))
                mrn = resolve_mrn(f"{tid}-{j}", vault_ready=vault_ready)
                batch.append({"id": pid, "mrn": mrn, "tid": tid})
                if j < 3:
                    sample_ids.append(pid)

            conn.execute(text(
                "INSERT INTO patients (id, mrn, tenant_id, is_active, created_at)"
                " VALUES (:id, :mrn, :tid, TRUE, NOW())"
                " ON CONFLICT (id) DO NOTHING"
            ), batch)
            patient_count += 1000
            patient_sample_ids[tid] = sample_ids

        print(f"  OK {patient_count} patients seeded (1000 x {len(TENANTS)} tenants)")

        # Phase 2 addition: one sample (already-completed) ingestion job,
        # 3 sample documents attached to it, and one active api_key, per
        # tenant — exercises the new tables end to end without requiring
        # the real ingestion pipeline (Phase 4+) to exist yet.
        job_count = 0
        doc_count = 0
        for tid in [TENANT_A, TENANT_B]:
            _set_tenant_context(conn, tid)
            engineer_id = user_ids[tid]["engineer"]

            job_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-job-{tid}"))
            conn.execute(text(
                "INSERT INTO ingestion_jobs"
                " (id, name, status, source_type, source_config, doc_count_total,"
                "  doc_count_processed, created_by, tenant_id, started_at, completed_at)"
                " VALUES (:id, 'seed-batch-001', 'completed', 's3_batch', :cfg, 3, 3,"
                "  :uid, :tid, NOW() - INTERVAL '1 hour', NOW())"
                " ON CONFLICT (id) DO NOTHING"
            ), {
                "id": job_id,
                "cfg": '{"s3_uri": "r2://pvh-documents-dev/seed/", "document_types": ["clinical_note"]}',
                "uid": engineer_id,
                "tid": tid,
            })
            job_count += 1

            for k, patient_id in enumerate(patient_sample_ids[tid]):
                doc_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-doc-{tid}-{k}"))
                conn.execute(text(
                    "INSERT INTO documents"
                    " (id, patient_id, document_type, source_path, ingestion_job_id,"
                    "  embedding_status, chunk_count, model_version, tenant_id)"
                    " VALUES (:id, :pid, :dtype, :src, :job, 'completed', 4,"
                    "  'text-embedding-3-large', :tid)"
                    " ON CONFLICT (id) DO NOTHING"
                ), {
                    "id": doc_id,
                    "pid": patient_id,
                    "dtype": DOCUMENT_TYPES[k % len(DOCUMENT_TYPES)],
                    "src": f"r2://pvh-documents-dev/seed/{tid}/{doc_id}/original.txt",
                    "job": job_id,
                    "tid": tid,
                })
                doc_count += 1

            admin_id = user_ids[tid]["admin"]
            raw_key, key_hash = fake_api_key_hash(tid[-4:])
            key_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"seed-key-{tid}"))
            conn.execute(text(
                "INSERT INTO api_keys"
                " (id, key_hash, name, scopes, user_id, tenant_id, expires_at, is_revoked)"
                " VALUES (:id, :hash, 'seed-service-key', :scopes, :uid, :tid, :exp, FALSE)"
                " ON CONFLICT (id) DO NOTHING"
            ), {
                "id": key_id,
                "hash": key_hash,
                "scopes": ["ingest:write", "query:read"],
                "uid": admin_id,
                "tid": tid,
                "exp": datetime.now(timezone.utc) + timedelta(days=90),
            })
            seed_api_keys.append((tid, raw_key))

        print(f"  OK {job_count} ingestion_jobs seeded, {doc_count} documents seeded")
        print(f"  OK {len(seed_api_keys)} api_keys seeded")

        conn.commit()

    print("")
    print("  Seed complete:")
    print(f"    Tenants        : {len(TENANTS)}")
    print(f"    Users          : {user_count}")
    print(f"    Patients       : {patient_count}")
    print(f"    Ingestion jobs : {job_count}")
    print(f"    Documents      : {doc_count}")
    print(f"    API keys       : {len(seed_api_keys)}")
    print("")
    print("  Dev credentials:")
    for t in ["tenant1", "tenant2"]:
        for role in ROLES:
            print(f"    {role}@{t}.test  (Keycloak password: test-password-123)")
    print("")
    print("  Seed API keys (plaintext shown once — dev/test use only, never real secrets):")
    for tid, raw_key in seed_api_keys:
        label = "Acme Health" if tid == TENANT_A else "Riverside Medical"
        print(f"    {label:<20} {raw_key}")
    print("")
    print("  NOTE: resolving these via X-API-Key will 401 until the BYPASSRLS")
    print("  grant in docs/adr/ADR-010-api-key-auth-rls-bootstrap.md is applied")
    print("  to this database (local docker-compose's superuser 'pvh' role is")
    print("  the one documented exception — it already bypasses RLS).")
    print("")
    print("  Verify counts (RLS-aware): python scripts/verify_seed.py")


if __name__ == "__main__":
    print("Seeding PatientVectorHub test data...")
    seed()
