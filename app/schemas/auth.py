from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.user import UserMe


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    requires_totp: bool = False
    totp_enabled: bool = False
    user: UserMe


class TelegramStartOut(BaseModel):
    token: str
    login_url: str
    expires_in: int


class TelegramPollIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)


class TelegramPollOut(BaseModel):
    status: Literal["pending", "confirmed"]
    tokens: TokenPair | None = None


class TelegramDevConfirmIn(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    telegram_id: int
    phone: str
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=512)


class LogoutIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=512)


class TotpCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_url: str
    issuer: str


class AuthProviderOut(BaseModel):
    code: str
    name: str
    enabled: bool


class AuthProvidersOut(BaseModel):
    providers: list[AuthProviderOut]


class TotpStatusOut(BaseModel):
    enabled: bool
    confirmed_at: datetime | None = None
