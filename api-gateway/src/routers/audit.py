"""
PatientVectorHub — audit log routes (Phase 8 / ADR-015).

main.py's own "Phase 8+ routers" comment named this file specifically —
audit was the one router genuinely deferred past its logical phase
(unlike query, which ADR-014 confirmed should mount the same phase it
was built): compliance/audit-trail retrieval is real later-phase work,
not something earlier phases needed to unblock anything else on.

Role model (matches doc 05's Role table, not a strict admin/auditor-only
gate): require_min_role("auditor") is the entry floor — everyone except
readonly passes that check — but non-admin/auditor callers are then
forced to their own user_id inside the handler regardless of what filter
they requested. This gives:
  - admin / auditor: full tenant audit trail, any filter
  - analyst / engineer: their own actions only ("Can read audit logs for
    own queries only" — doc 05)
  - readonly: blocked entirely (403 at the dependency)

Export is a stricter, separate gate: require_role("admin", "auditor")
exact-match only, no self-scoping fallback — bulk extraction of the full
audit trail is compliance-evidence territory (doc 01's "compliance
officer... demonstrate HIPAA compliance on demand" story), not a
self-service feature for analysts/engineers to pull their own history.
Every export call itself writes a `data_export` audit_logs row —
audit_logs.action already reserved that exact enum value (migration 004)
with no caller until now.
"""

from __future__ import annotations

import csv
import datetime
import io
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from starlette.responses import Response as StarletteResponse

from ..db import crud
from ..deps import get_current_user, get_db
from ..middleware.rate_limit import limiter
from ..middleware.rbac import require_min_role, require_role
from ..schemas.audit import AuditLogEntry, AuditLogListResponse

router = APIRouter()

# Fixed, not derived from result rows — csv.DictWriter needs fieldnames
# up front, and deriving them from rows[0] breaks outright on an empty
# (zero-match) export. Matches AuditLogEntry's field order exactly.
_EXPORT_FIELDS = [
    "id", "user_id", "action", "patient_id", "ip_address",
    "request_id", "status_code", "created_at",
]

# Safety cap on export size — GET /logs/export has no limit/offset (it's
# meant to return "everything matching the filter", per its compliance-
# evidence purpose), but an unbounded query against a large audit_logs
# table is still a real risk. 10,000 rows is generous for a filtered
# compliance pull; a genuinely larger export is a case for direct DB
# access / a background job, not a synchronous HTTP request — not solved
# in this phase, just bounded so it fails safely instead of hanging.
_EXPORT_ROW_CAP = 10_000


def _serialize_log_row(row: dict) -> dict:
    """UUID/datetime -> str, matching the explicit-serialization pattern
    already established in routers/admin.py's list_keys/get_users
    (str(...) / .isoformat() called explicitly rather than relying on
    implicit Pydantic coercion for these fields)."""
    out = dict(row)
    for key in ("id", "user_id", "patient_id", "request_id"):
        if isinstance(out.get(key), uuid.UUID):
            out[key] = str(out[key])
    created_at = out.get("created_at")
    if isinstance(created_at, datetime.datetime):
        out["created_at"] = created_at.isoformat()
    return out


def _resolve_effective_user_id(user: dict, requested_user_id: str | None) -> str | None:
    """admin/auditor: pass whatever the caller asked for (including None
    = no filter). Anyone else who reached this far (require_min_role
    already blocked readonly): forced to their own user_id, silently
    overriding any different value they tried to request — a non-admin/
    auditor caller asking to filter by someone else's user_id gets their
    OWN logs back, not a 403 and not someone else's data; matches
    list_ingestion_jobs-style filtering-not-erroring precedent elsewhere
    in this codebase rather than surfacing a confusing permission error
    for what is, from the caller's side, just an unusable filter value.
    """
    if user["role"] in ("admin", "auditor"):
        return requested_user_id
    return user["user_id"]


@router.get("/logs", response_model=AuditLogListResponse, dependencies=[require_min_role("auditor")])
@limiter.limit("200/minute")
async def get_audit_logs(
    request: Request,
    response: Response,
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    from_ts: str | None = Query(default=None, description="ISO-8601, inclusive lower bound"),
    to_ts: str | None = Query(default=None, description="ISO-8601, inclusive upper bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> AuditLogListResponse:
    effective_user_id = _resolve_effective_user_id(user, user_id)
    result = await crud.list_audit_logs(
        db,
        action=action,
        user_id=effective_user_id,
        patient_id=patient_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        logs=[AuditLogEntry(**_serialize_log_row(r)) for r in result["logs"]],
        total=result["total"],
        limit=limit,
        offset=offset,
    )


@router.get("/logs/export", dependencies=[require_role("admin", "auditor")])
@limiter.limit("10/minute")
async def export_audit_logs(
    request: Request,
    response: Response,
    action: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    patient_id: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    format: str = Query(default="csv", pattern="^(csv|json)$"),
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> StarletteResponse:
    result = await crud.list_audit_logs(
        db,
        action=action,
        user_id=user_id,  # admin/auditor only reach this route (RBAC gate above) — no self-scoping
        patient_id=patient_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=_EXPORT_ROW_CAP,
        offset=0,
    )
    rows = [_serialize_log_row(r) for r in result["logs"]]

    # The export itself is the compliance-relevant event here — logged
    # AFTER the query succeeds (a failed export attempt, e.g. a bad date
    # filter causing a DB error, never reaches this line and is not
    # logged as a completed export).
    await crud.write_audit_log(
        db,
        action="data_export",
        user_id=user["user_id"],
        metadata={
            "export_format": format,
            "row_count": len(rows),
            "truncated": result["total"] > _EXPORT_ROW_CAP,
            "filters": {
                "action": action, "user_id": user_id, "patient_id": patient_id,
                "from_ts": from_ts, "to_ts": to_ts,
            },
        },
    )

    filename_stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if format == "json":
        import json as _json

        body = _json.dumps({"logs": rows, "total": result["total"], "exported": len(rows)})
        return StarletteResponse(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="audit-logs-{filename_stamp}.json"'},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field) for field in _EXPORT_FIELDS})
    return StarletteResponse(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-logs-{filename_stamp}.csv"'},
    )
