from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    telegram_id: int | None = None
    telegram_username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str
    phone: str | None = None
    phone_verified: bool = False
    email: str | None = None
    email_verified: bool = False
    status: str
    notification_settings: dict = Field(default_factory=dict)
    platform_roles: list[str] = Field(default_factory=list)
    created_at: datetime


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    full_name: str
    telegram_username: str | None = None
    is_private_person: bool = False


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=128)
    last_name: str | None = Field(default=None, max_length=128)
    email: str | None = Field(default=None, max_length=255)
    notification_settings: dict[str, bool] | None = None


class NotificationSettings(BaseModel):
    new_listing_moderated: bool = True
    new_complaint: bool = True
    new_invitation: bool = True
    listing_expiring: bool = True
