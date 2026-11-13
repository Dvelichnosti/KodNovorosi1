from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSON_TYPE, Base, TimestampMixin
from app.models.base import UUIDPrimaryKeyMixin, enum_type
from app.models.enums import (
    DocumentKind,
    DocumentStatus,
    InvitationStatus,
    MemberStatus,
    OrgStatus,
    OrgType,
    Region,
    VerificationLevel,
)


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    type: Mapped[OrgType] = mapped_column(enum_type(OrgType), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inn: Mapped[str | None] = mapped_column(String(12), unique=True, index=True)
    ogrn: Mapped[str | None] = mapped_column(String(15), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(512))
    region: Mapped[Region] = mapped_column(enum_type(Region), nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(512))
    website: Mapped[str | None] = mapped_column(String(512))
    phone: Mapped[str | None] = mapped_column(String(20))
    telegram: Mapped[str | None] = mapped_column(String(128))
    max_contact: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[OrgStatus] = mapped_column(
        enum_type(OrgStatus), default=OrgStatus.ACTIVE, nullable=False, index=True
    )
    verification_level: Mapped[VerificationLevel] = mapped_column(
        enum_type(VerificationLevel),
        default=VerificationLevel.NONE,
        nullable=False,
        index=True,
    )
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inn_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderator_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plans.id", ondelete="SET NULL")
    )
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    plan: Mapped["Plan | None"] = relationship(lazy="joined")  # noqa: F821
    members: Mapped[list[OrgMember]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    roles: Mapped[list[OrgRole]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )
    capabilities: Mapped[list[OrganizationCapability]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    documents: Mapped[list[VerificationDocument]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
    )


class OrgMember(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_members_org_user"),
        Index("ix_org_members_user_status", "user_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("org_roles.id", ondelete="SET NULL")
    )
    is_owner: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[MemberStatus] = mapped_column(
        enum_type(MemberStatus), default=MemberStatus.ACTIVE, nullable=False
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(  # noqa: F821
        back_populates="memberships", foreign_keys=[user_id], lazy="joined"
    )
    role: Mapped[OrgRole | None] = relationship(lazy="joined")


class OrgRole(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "org_roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_roles_org_name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    is_system: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    organization: Mapped[Organization] = relationship(back_populates="roles")


class Invitation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("org_roles.id", ondelete="SET NULL")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    telegram_id: Mapped[int | None] = mapped_column(index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        enum_type(InvitationStatus), default=InvitationStatus.PENDING, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    organization: Mapped[Organization] = relationship(lazy="joined")
    role: Mapped[OrgRole | None] = relationship(lazy="joined")


class Capability(Base):
    __tablename__ = "capabilities"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    param_schema: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class OrganizationCapability(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "organization_capabilities"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_org_capabilities_org_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(
        ForeignKey("capabilities.code", ondelete="CASCADE"), nullable=False, index=True
    )
    params: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    organization: Mapped[Organization] = relationship(back_populates="capabilities")
    capability: Mapped[Capability] = relationship(lazy="joined")


class VerificationDocument(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "verification_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[DocumentKind] = mapped_column(
        enum_type(DocumentKind), default=DocumentKind.OTHER, nullable=False
    )
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[DocumentStatus] = mapped_column(
        enum_type(DocumentStatus), default=DocumentStatus.PENDING, nullable=False, index=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="documents")
