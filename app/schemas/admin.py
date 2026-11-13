from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class PlatformRoleOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    permissions: list[str] = Field(default_factory=list)
    is_system: bool
    users_count: int = 0


class PlatformRoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=128)
    permissions: list[str] = Field(default_factory=list)


class PlatformRoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    permissions: list[str] | None = None


class AssignPlatformRoleIn(BaseModel):
    role_id: uuid.UUID


class BlockUserIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class AdminUserOut(BaseModel):
    id: uuid.UUID
    telegram_id: int | None = None
    full_name: str
    phone: str | None = None
    email: str | None = None
    status: str
    platform_roles: list[str] = Field(default_factory=list)
    organizations_count: int = 0
    created_at: datetime
    last_login_at: datetime | None = None
    blocked_reason: str | None = None


class AdminUserListOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    per_page: int
    pages: int


class ResolveComplaintIn(BaseModel):
    status: str = Field(pattern="^(resolved|rejected)$")
    resolution: str = Field(min_length=3, max_length=2000)


class AuditOut(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    action: str
    entity_type: str
    entity_id: str | None = None
    payload: dict = Field(default_factory=dict)
    ip: str | None = None
    created_at: datetime


class SettingOut(BaseModel):
    key: str
    value: dict
    description: str | None = None
    updated_at: datetime


class SettingUpdateIn(BaseModel):
    value: dict
    description: str | None = Field(default=None, max_length=500)


class AdminStatsOut(BaseModel):
    users_total: int
    users_blocked: int
    organizations_total: int
    organizations_pending_verification: int
    listings_total: int
    listings_pending: int
    listings_active: int
    complaints_new: int
    documents_pending: int


class PlanCreateIn(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=128)
    max_active_listings: int = Field(ge=0, le=100000)
    price: float = Field(default=0, ge=0)
    currency: str = Field(default="RUB", max_length=3)
    features: dict = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    sort_order: int = 0


class PlanUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    max_active_listings: int | None = Field(default=None, ge=0, le=100000)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    features: dict | None = None
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    sort_order: int | None = None
