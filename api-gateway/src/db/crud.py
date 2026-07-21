"""
PatientVectorHub — async CRUD operations.

Every function here takes an AsyncSession that MUST already be scoped via
db.session.get_tenant_session() (that's what deps.get_db() hands routes),
except the small `tenants`-only and API-key-resolution functions explicitly
marked otherwise below.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import secrets
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .session import get_untenanted_session

# ── Tenants (root table — not RLS-scoped) ───────────────────────────────────


async def list_tenants() -> list[dict]:
    async with get_untenanted_session() as db:
        rows = (
            await db.execute(text("SELECT id, name, namespace, plan, created_at FROM tenants"))
        ).mappings().all()
        return [dict(r) for r in rows]


# ── Users ────────────────────────────────────────────────────────────────


async def get_user_by_keycloak_sub(db: AsyncSession, keycloak_subject: str) -> dict | None:
    row = (
        await db.execute(
            text(
                "SELECT id, email, role, tenant_id, is_active"
                " FROM users WHERE keycloak_subject = :ks"
            ),
            {"ks": keycloak_subject},
        )
    ).mappings().fetchone()
    return dict(row) if row else None


async def touch_user_last_login(db: AsyncSession, user_id: str) -> None:
    await db.execute(
        text("UPDATE users SET last_login = NOW() WHERE id = :uid"), {"uid": user_id}
    )


async def list_users(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT id, email, role, is_active, last_login, created_at"
                " FROM users ORDER BY created_at DESC"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ── API keys ─────────────────────────────────────────────────────────────


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def create_api_key(
    db: AsyncSession, *, name: str, scopes: list[str], expires_days: int, user_id: str
) -> dict:
    raw_key = f"pvh_{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(raw_key)
    key_id = str(uuid.uuid4())
    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=expires_days)
    await db.execute(
        text(
            "INSERT INTO api_keys"
            " (id, key_hash, name, scopes, user_id, tenant_id, expires_at)"
            " VALUES (:id, :hash, :name, :scopes, :uid,"
            " current_setting('app.tenant_id', true)::uuid, :exp)"
        ),
        {
            "id": key_id,
            "hash": key_hash,
            "name": name,
            "scopes": scopes,
            "uid": user_id,
            "exp": expires,
        },
    )
    # key_plaintext is returned exactly once — the caller must show it to
    # the user now and never persist it; only key_hash is ever stored.
    return {
        "key_id": key_id,
        "key_plaintext": raw_key,
        "name": name,
        "scopes": scopes,
        "expires_at": expires.isoformat(),
    }


async def revoke_api_key(db: AsyncSession, key_id: str) -> bool:
    result = await db.execute(
        text(
            "UPDATE api_keys SET is_revoked = TRUE"
            " WHERE id = :id AND tenant_id = current_setting('app.tenant_id', true)::uuid"
            " RETURNING id"
        ),
        {"id": key_id},
    )
    return result.rowcount > 0


async def list_api_keys(db: AsyncSession) -> list[dict]:
    """Never returns key_hash or any reconstructible secret — listing
    endpoints only need metadata for the admin UI's revoke/rotate flow."""
    rows = (
        await db.execute(
            text(
                "SELECT id, name, scopes, user_id, expires_at, is_revoked, last_used_at,"
                " created_at FROM api_keys ORDER BY created_at DESC"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def resolve_api_key(raw_key: str) -> dict | None:
    """Look up which tenant/user a raw X-API-Key belongs to.

    See ADR-010 and migrations/versions/004_add_core_tables.py for why
    this is a dedicated, RLS-bypassing SQL function rather than a normal
    tenant-scoped query — you don't know the tenant until this call
    resolves it, so a normal get_tenant_session() can't be used here.

    IMPORTANT: resolve_api_key_tenant() only bypasses RLS when its owning
    role is a Postgres superuser (true immediately in local dev — see
    ADR-010) or has been separately granted BYPASSRLS *and* a plain SELECT
    on api_keys by a DB admin, out of band (required on managed Postgres —
    Aiven, RDS, etc.). Until that's true in a given environment, this
    returns None for every key — API-key auth fails closed (401), it does
    not fall back to some less-safe path. Do not "fix" that by loosening
    the RLS policy on api_keys; provision the role instead (ADR-010).
    """
    key_hash = _hash_key(raw_key)
    async with get_untenanted_session() as db:
        row = (
            await db.execute(
                text("SELECT * FROM resolve_api_key_tenant(:hash)"), {"hash": key_hash}
            )
        ).mappings().fetchone()
    if not row or row["is_revoked"]:
        return None
    if row["expires_at"] and row["expires_at"] < datetime.datetime.now(datetime.timezone.utc):
        return None
    return dict(row)


# ── Ingestion jobs ───────────────────────────────────────────────────────


async def create_ingestion_job(
    db: AsyncSession, *, name: str, source_type: str, source_config: dict, created_by: str
) -> dict:
    jid = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO ingestion_jobs"
            " (id, name, status, source_type, source_config, created_by, tenant_id)"
            " VALUES (:id, :name, 'queued', :src, :cfg, :uid,"
            " current_setting('app.tenant_id', true)::uuid)"
        ),
        # json.dumps() is required here: asyncpg (unlike psycopg2) does not
        # auto-adapt a Python dict for a JSONB column when going through
        # SQLAlchemy's raw text() path — confirmed live, it otherwise fails
        # with "asyncpg.exceptions.DataError: invalid input for query
        # argument $N: {...} ('dict' object has no attribute 'encode')".
        {"id": jid, "name": name, "src": source_type, "cfg": json.dumps(source_config), "uid": created_by},
    )
    return {"id": jid, "status": "queued"}


async def get_ingestion_job(db: AsyncSession, job_id: str) -> dict | None:
    row = (
        await db.execute(
            text(
                "SELECT id, name, status, source_type, doc_count_total,"
                " doc_count_processed, doc_count_failed, error_message,"
                " started_at, completed_at, created_at"
                " FROM ingestion_jobs WHERE id = :jid"
            ),
            {"jid": job_id},
        )
    ).mappings().fetchone()
    if not row:
        return None
    total = max(row["doc_count_total"] or 1, 1)
    pct = round(row["doc_count_processed"] / total * 100, 1)
    return {**dict(row), "progress_pct": pct}


async def list_ingestion_jobs(db: AsyncSession, status: str | None = None) -> list[dict]:
    where = "WHERE status = :status" if status else ""
    rows = (
        await db.execute(
            text(
                f"SELECT id, name, status, doc_count_total, doc_count_processed,"
                f" doc_count_failed, created_at FROM ingestion_jobs {where}"
                f" ORDER BY created_at DESC LIMIT 100"
            ),
            {"status": status} if status else {},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ── Documents ────────────────────────────────────────────────────────────


async def create_document(
    db: AsyncSession,
    *,
    patient_id: str,
    document_type: str,
    source_path: str,
    ingestion_job_id: str | None = None,
) -> dict:
    doc_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO documents"
            " (id, patient_id, document_type, source_path, ingestion_job_id, tenant_id)"
            " VALUES (:id, :pid, :dtype, :src, :job,"
            " current_setting('app.tenant_id', true)::uuid)"
        ),
        {
            "id": doc_id,
            "pid": patient_id,
            "dtype": document_type,
            "src": source_path,
            "job": ingestion_job_id,
        },
    )
    return {"id": doc_id, "embedding_status": "pending"}


async def count_documents_for_patient(db: AsyncSession, patient_id: str) -> int:
    return (
        await db.execute(
            text("SELECT COUNT(*) FROM documents WHERE patient_id = :pid"), {"pid": patient_id}
        )
    ).scalar()


# ── Audit logs (INSERT + SELECT only — see models.AuditLog docstring) ──────


async def write_audit_log(
    db: AsyncSession,
    *,
    action: str,
    user_id: str | None = None,
    api_key_id: str | None = None,
    patient_id: str | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    status_code: int | None = None,
    metadata: dict | None = None,
) -> None:
    await db.execute(
        text(
            "INSERT INTO audit_logs"
            " (id, user_id, api_key_id, action, patient_id, ip_address,"
            "  request_id, status_code, metadata, tenant_id)"
            " VALUES (gen_random_uuid(), :uid, :kid, :act, :pid, :ip,"
            "  :req, :code, :meta, current_setting('app.tenant_id', true)::uuid)"
        ),
        {
            "uid": user_id,
            "kid": api_key_id,
            "act": action,
            "pid": patient_id,
            "ip": ip_address,
            "req": request_id,
            "code": status_code,
            "meta": json.dumps(metadata or {}),
        },
    )


async def list_audit_logs(
    db: AsyncSession,
    *,
    action: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    conditions = ["1=1"]
    params: dict = {"lim": limit, "off": offset}
    if action:
        conditions.append("action = :action")
        params["action"] = action
    if user_id:
        conditions.append("user_id = :uid")
        params["uid"] = user_id
    where = " AND ".join(conditions)

    rows = (
        await db.execute(
            text(
                f"SELECT id, user_id, action, patient_id, ip_address, request_id,"
                f" status_code, created_at FROM audit_logs WHERE {where}"
                f" ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            params,
        )
    ).mappings().all()
    total = (
        await db.execute(
            text(f"SELECT COUNT(*) FROM audit_logs WHERE {where}"),
            {k: v for k, v in params.items() if k not in ("lim", "off")},
        )
    ).scalar()
    return {"logs": [dict(r) for r in rows], "total": total}


# ── Query logs ───────────────────────────────────────────────────────────


async def log_query(
    db: AsyncSession,
    *,
    user_id: str | None,
    query_text: str,
    result_count: int,
    latency_ms: int,
    model_version: str | None = None,
) -> None:
    await db.execute(
        text(
            "INSERT INTO query_logs"
            " (id, tenant_id, user_id, query_text_hash, result_count, latency_ms, model_version)"
            " VALUES (gen_random_uuid(), current_setting('app.tenant_id', true)::uuid,"
            " :uid, :hash, :rc, :lat, :mv)"
        ),
        {
            "uid": user_id,
            "hash": hashlib.sha256(query_text.encode()).hexdigest(),
            "rc": result_count,
            "lat": latency_ms,
            "mv": model_version,
        },
    )
