from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSON_TYPE, Base, TimestampMixin
from app.models.base import UUIDPrimaryKeyMixin, enum_type
from app.models.enums import UserStatus


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus), default=UserStatus.ACTIVE, nullable=False, index=True
    )
    blocked_reason: Mapped[str | None] = mapped_column(Text)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_settings: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    platform_role_links: Mapped[list[UserPlatformRole]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="UserPlatformRole.user_id",
    )
    memberships: Mapped[list["OrgMember"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="OrgMember.user_id",
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name or "", self.last_name or ""]
        result = " ".join(part for part in parts if part).strip()
        return result or (self.telegram_username or "Пользователь")

    @property
    def platform_roles(self) -> list["PlatformRole"]:
        return [link.role for link in self.platform_role_links if link.role is not None]

    @property
    def is_platform_user(self) -> bool:
        return bool(self.platform_role_links)


class PlatformRole(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "platform_roles"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    permissions: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    user_links: Mapped[list[UserPlatformRole]] = relationship(
        back_populates="role",
        cascade="all, delete-orphan",
    )


class UserPlatformRole(Base):
    __tablename__ = "user_platform_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    user: Mapped[User] = relationship(
        back_populates="platform_role_links",
        foreign_keys=[user_id],
    )
    role: Mapped[PlatformRole] = relationship(back_populates="user_links", lazy="joined")


class TotpSecret(Base):
    __tablename__ = "totp_secrets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    user: Mapped[User] = relationship()
