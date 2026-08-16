"""Pydantic response models for api-gateway/src/routers/audit.py (Phase 8).

Field set matches what crud.list_audit_logs already selects (see
db/crud.py) — id, user_id, action, patient_id, ip_address, request_id,
status_code, created_at. patient_id stays a bare `str | None`, not
blurred/masked here: PHI display formatting (the dashboard's
`.phi-cell { filter: blur(4px) }` treatment) is a frontend concern per
doc 04's UI/UX brief, not something the API response itself should
degrade — an API consumer legitimately entitled to call this endpoint
(admin/auditor, or an analyst/engineer viewing their own actions) is
entitled to the real value; blurring the value server-side would remove
the API's usefulness as tamper-evident audit evidence, which is the
entire point of a HIPAA audit trail per doc 01's compliance-officer user
story.
"""

from __future__ import annotations

from pydantic import BaseModel


class AuditLogEntry(BaseModel):
    id: str
    user_id: str | None
    action: str
    patient_id: str | None
    ip_address: str | None
    request_id: str | None
    status_code: int | None
    created_at: str


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogEntry]
    total: int
    limit: int
    offset: int
