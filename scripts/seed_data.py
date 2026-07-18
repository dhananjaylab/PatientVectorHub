#!/usr/bin/env python3
"""
Seed synthetic test data - NO real PHI.
Creates: 2 tenants, 4 users per tenant (one per role), 1000 patients per tenant.
Safe to run multiple times (ON CONFLICT DO NOTHING).
"""
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid
import hashlib

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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


def fake_mrn(seed: str) -> str:
    """Return a Vault-ciphertext-style placeholder - never real PHI."""
    h = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    return f"vault:v1:SEED_{h}"


def seed() -> None:
    try:
        from sqlalchemy import create_engine, text
    except ImportError:
        print("SQLAlchemy not installed - cannot seed")
        sys.exit(1)

    engine = create_engine(get_database_url(), echo=False, pool_pre_ping=True)

    print("Connecting to configured PostgreSQL database...")
    with engine.connect() as conn:
        print("Connected. Seeding rows...")
        # Tenants
        for t in TENANTS:
            conn.execute(text(
                "INSERT INTO tenants (id, name, namespace, plan, created_at)"
                " VALUES (:id, :name, :ns, 'enterprise', NOW())"
                " ON CONFLICT (id) DO NOTHING"
            ), {"id": t["id"], "name": t["name"], "ns": t["namespace"]})
        print(f"  OK {len(TENANTS)} tenants seeded")

        # Users (one per role per tenant)
        user_count = 0
        for i, tid in enumerate([TENANT_A, TENANT_B]):
            tenant_label = f"tenant{i + 1}"
            for role in ROLES:
                uid = str(uuid.uuid5(
                    uuid.NAMESPACE_DNS, f"{role}@{tenant_label}.test"
                ))
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

        # Patients (1000 per tenant)
        patient_count = 0
        for tid in [TENANT_A, TENANT_B]:
            batch = []
            for j in range(1000):
                pid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"patient-{tid}-{j}"))
                mrn = fake_mrn(f"{tid}-{j}")
                batch.append({"id": pid, "mrn": mrn, "tid": tid})

            conn.execute(text(
                "INSERT INTO patients (id, mrn, tenant_id, is_active, created_at)"
                " VALUES (:id, :mrn, :tid, TRUE, NOW())"
                " ON CONFLICT (id) DO NOTHING"
            ), batch)
            patient_count += 1000

        print(f"  OK {patient_count} patients seeded (1000 x {len(TENANTS)} tenants)")

        conn.commit()

    print("")
    print("  Seed complete:")
    print(f"    Tenants  : {len(TENANTS)}")
    print(f"    Users    : {user_count}")
    print(f"    Patients : {patient_count}")
    print("")
    print("  Dev credentials:")
    for t in ["tenant1", "tenant2"]:
        for role in ROLES:
            print(f"    {role}@{t}.test  (Keycloak password: test-password-123)")


if __name__ == "__main__":
    print("Seeding PatientVectorHub test data...")
    seed()
