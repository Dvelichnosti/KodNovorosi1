from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ListingType, Region
from app.schemas.catalog import CategoryShort
from app.schemas.organization import OrgBrief
from app.schemas.user import UserPublic


class ListingContacts(BaseModel):
    phone: str | None = None
    telegram: str | None = None
    max_contact: str | None = None


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    type: str
    starts_at: datetime
    ends_at: datetime | None = None


class ListingCreate(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    description: str = Field(min_length=10, max_length=20000)
    category_id: uuid.UUID
    type: ListingType
    region: Region
    city: str | None = Field(default=None, max_length=128)
    address: str | None = Field(default=None, max_length=512)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="RUB", max_length=3)
    price_unit: str | None = Field(default=None, max_length=32)
    negotiable: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)
    organization_id: uuid.UUID | None = None
    contact_phone: str | None = Field(default=None, max_length=20)
    contact_telegram: str | None = Field(default=None, max_length=128)
    contact_max: str | None = Field(default=None, max_length=128)

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ListingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=255)
    description: str | None = Field(default=None, min_length=10, max_length=20000)
    category_id: uuid.UUID | None = None
    type: ListingType | None = None
    region: Region | None = None
    city: str | None = Field(default=None, max_length=128)
    address: str | None = Field(default=None, max_length=512)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=3)
    price_unit: str | None = Field(default=None, max_length=32)
    negotiable: bool | None = None
    attributes: dict[str, Any] | None = None
    contact_phone: str | None = Field(default=None, max_length=20)
    contact_telegram: str | None = Field(default=None, max_length=128)
    contact_max: str | None = Field(default=None, max_length=128)


class ListingOut(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    category: CategoryShort | None = None
    organization: OrgBrief | None = None
    user: UserPublic | None = None
    type: str
    region: str
    city: str | None = None
    address: str | None = None
    price: float | None = None
    currency: str
    price_unit: str | None = None
    negotiable: bool
    attributes: dict[str, Any] = Field(default_factory=dict)
    status: str
    rejection_reason: str | None = None
    is_private_person: bool = False
    contacts: ListingContacts | None = None
    contacts_available: bool = False
    promotions: list[PromotionOut] = Field(default_factory=list)
    is_top: bool = False
    is_highlight: bool = False
    published_at: datetime | None = None
    expires_at: datetime | None = None
    bumped_at: datetime | None = None
    views_count: int = 0
    favorites_count: int = 0
    is_favorite: bool = False
    created_at: datetime
    updated_at: datetime


class ListingStatsOut(BaseModel):
    listing_id: uuid.UUID
    total_views: int
    views_7d: int
    views_30d: int
    favorites_count: int
    status: str
    published_at: datetime | None = None
    expires_at: datetime | None = None


class ComplaintCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=64)
    comment: str | None = Field(default=None, max_length=2000)


class ComplaintOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    target_user_id: uuid.UUID | None = None
    reason: str
    comment: str | None = None
    status: str
    resolution: str | None = None
    complainant: UserPublic | None = None
    created_at: datetime
    handled_at: datetime | None = None


class ModerationRejectIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ModerationBlockIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class PromotionCreateIn(BaseModel):
    type: str = Field(pattern="^(top|highlight|bump)$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ListingSearchParams(BaseModel):
    q: str | None = None
    category_id: uuid.UUID | None = None
    type: ListingType | None = None
    region: Region | None = None
    price_min: float | None = Field(default=None, ge=0)
    price_max: float | None = Field(default=None, ge=0)
    organization_id: uuid.UUID | None = None
    sort: str = Field(default="date", pattern="^(date|price_asc|price_desc|relevance)$")


class ListingShort(BaseModel):
    id: uuid.UUID
    title: str
    price: float | None = None
    currency: str = "RUB"
    region: str
    type: str
    category: CategoryShort | None = None
    organization: OrgBrief | None = None
    published_at: datetime | None = None
    is_top: bool = False
    is_highlight: bool = False
    is_favorite: bool = False
