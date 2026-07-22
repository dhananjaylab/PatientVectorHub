"""Pydantic request/response models for api-gateway/src/routers/admin.py."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CreateApiKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(..., min_length=1)
    expires_days: int = Field(default=90, ge=1, le=365)


class CreateApiKeyResponse(BaseModel):
    key_id: str
    key_plaintext: str  # shown exactly once — caller must store it now
    name: str
    scopes: list[str]
    expires_at: str


class ApiKeySummary(BaseModel):
    id: str
    name: str
    scopes: list[str]
    user_id: str
    expires_at: str
    is_revoked: bool
    last_used_at: str | None = None
    created_at: str


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeySummary]


class UserSummary(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    last_login: str | None = None
    created_at: str


class UserListResponse(BaseModel):
    users: list[UserSummary]
