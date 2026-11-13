from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import OrgType, Region


class OrgCreate(BaseModel):
    type: OrgType
    name: str = Field(min_length=2, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    ogrn: str | None = Field(default=None, max_length=15)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=512)
    region: Region
    address: str | None = Field(default=None, max_length=512)
    website: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=20)
    telegram: str | None = Field(default=None, max_length=128)
    max_contact: str | None = Field(default=None, max_length=128)
    slug: str | None = Field(default=None, max_length=160)
    capabilities: list["CapabilityIn"] = Field(default_factory=list)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    type: OrgType | None = None
    inn: str | None = Field(default=None, max_length=12)
    ogrn: str | None = Field(default=None, max_length=15)
    description: str | None = Field(default=None, max_length=5000)
    logo_url: str | None = Field(default=None, max_length=512)
    region: Region | None = None
    address: str | None = Field(default=None, max_length=512)
    website: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=20)
    telegram: str | None = Field(default=None, max_length=128)
    max_contact: str | None = Field(default=None, max_length=128)
    slug: str | None = Field(default=None, max_length=160)


class CapabilityIn(BaseModel):
    code: str = Field(min_length=2, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class CapabilitiesUpdate(BaseModel):
    capabilities: list[CapabilityIn] = Field(default_factory=list)


class CapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    code: str
    name: str
    param_schema: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class OrgCapabilityOut(BaseModel):
    code: str
    name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    code: str
    name: str
    max_active_listings: int
    price: float
    currency: str
    features: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None
    is_active: bool
    sort_order: int = 0


class OrgBrief(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    type: str
    region: str
    logo_url: str | None = None
    verification_level: str


class OrgOut(BaseModel):
    id: uuid.UUID
    slug: str
    type: str
    name: str
    inn: str | None = None
    ogrn: str | None = None
    description: str | None = None
    logo_url: str | None = None
    region: str
    address: str | None = None
    website: str | None = None
    phone: str | None = None
    telegram: str | None = None
    max_contact: str | None = None
    status: str
    verification_level: str
    verification_label: str | None = None
    phone_verified: bool = False
    inn_verified: bool = False
    moderator_verified: bool = False
    rejection_reason: str | None = None
    plan: PlanOut | None = None
    capabilities: list[OrgCapabilityOut] = Field(default_factory=list)
    members_count: int = 0
    active_listings_count: int = 0
    created_at: datetime


class OrgPublic(BaseModel):
    id: uuid.UUID
    slug: str
    type: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    region: str
    address: str | None = None
    website: str | None = None
    phone: str | None = None
    telegram: str | None = None
    max_contact: str | None = None
    verification_level: str
    verification_label: str | None = None
    capabilities: list[OrgCapabilityOut] = Field(default_factory=list)
    active_listings_count: int = 0
    owner_name: str | None = None
    created_at: datetime


class RoleOut(BaseModel):
    id: uuid.UUID
    name: str
    permissions: list[str] = Field(default_factory=list)
    is_system: bool
    members_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=128)
    permissions: list[str] | None = None


class MemberOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    telegram_username: str | None = None
    phone: str | None = None
    role: RoleOut | None = None
    is_owner: bool
    status: str
    joined_at: datetime


class MemberUpdate(BaseModel):
    role_id: uuid.UUID | None = None


class InviteIn(BaseModel):
    role_id: uuid.UUID | None = None
    telegram_id: int | None = None


class InvitationCreated(BaseModel):
    id: uuid.UUID
    token: str
    invite_url: str
    expires_at: datetime


class InvitationOut(BaseModel):
    id: uuid.UUID
    role: RoleOut | None = None
    telegram_id: int | None = None
    status: str
    expires_at: datetime
    accepted_at: datetime | None = None
    created_at: datetime


class OwnerTransferIn(BaseModel):
    user_id: uuid.UUID


class InnVerifyIn(BaseModel):
    inn: str = Field(min_length=10, max_length=12)


class DocumentOut(BaseModel):
    id: uuid.UUID
    kind: str
    file_url: str
    original_name: str | None = None
    status: str
    review_comment: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class DocumentReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str | None = Field(default=None, max_length=2000)


class VerifyOrgIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str | None = Field(default=None, max_length=2000)


class AssignPlanIn(BaseModel):
    plan_id: uuid.UUID | None = None
    expires_at: datetime | None = None


class OrgListOut(OrgOut):
    pass


class OrgSearchParams(BaseModel):
    q: str | None = None
    region: Region | None = None
    type: OrgType | None = None
    capability: str | None = None
    verification_level: str | None = None

    @field_validator("q")
    @classmethod
    def clean_q(cls, value: str | None) -> str | None:
        return value.strip() if value else None
