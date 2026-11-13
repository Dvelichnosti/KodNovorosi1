from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSON_TYPE, Base, TimestampMixin
from app.models.base import UUIDPrimaryKeyMixin, enum_type
from app.models.enums import (
    ComplaintStatus,
    ListingStatus,
    ListingType,
    PromotionType,
    Region,
)


class Listing(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_status_published", "status", "published_at"),
        Index("ix_listings_category_status", "category_id", "status"),
        Index("ix_listings_region_status", "region", "status"),
        Index("ix_listings_org_status", "organization_id", "status"),
        Index("ix_listings_attributes", "attributes", postgresql_using="gin"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type: Mapped[ListingType] = mapped_column(
        enum_type(ListingType), nullable=False, index=True
    )
    region: Mapped[Region] = mapped_column(enum_type(Region), nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(512))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    price_unit: Mapped[str | None] = mapped_column(String(32))
    negotiable: Mapped[bool] = mapped_column(default=False, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)

    status: Mapped[ListingStatus] = mapped_column(
        enum_type(ListingStatus), default=ListingStatus.DRAFT, nullable=False, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    moderation_comment: Mapped[str | None] = mapped_column(Text)
    moderated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), index=True
    )
    is_private_person: Mapped[bool] = mapped_column(default=False, nullable=False)

    contact_phone: Mapped[str | None] = mapped_column(String(20))
    contact_telegram: Mapped[str | None] = mapped_column(String(128))
    contact_max: Mapped[str | None] = mapped_column(String(128))

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    bumped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    views_count: Mapped[int] = mapped_column(default=0, nullable=False)
    favorites_count: Mapped[int] = mapped_column(default=0, nullable=False)

    category: Mapped["Category"] = relationship(lazy="joined")  # noqa: F821
    organization: Mapped["Organization | None"] = relationship(lazy="joined")  # noqa: F821
    user: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[user_id], lazy="joined"
    )
    promotions: Mapped[list[ListingPromotion]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ListingPromotion(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "listing_promotions"
    __table_args__ = (
        Index("ix_listing_promotions_listing_type", "listing_id", "type"),
    )

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[PromotionType] = mapped_column(enum_type(PromotionType), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    listing: Mapped[Listing] = relationship(back_populates="promotions")


class ListingView(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "listing_views"
    __table_args__ = (Index("ix_listing_views_listing_created", "listing_id", "created_at"),)

    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class Favorite(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint("user_id", "listing_id", name="uq_favorites_user_listing"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )


class Complaint(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "complaints"
    __table_args__ = (Index("ix_complaints_status_created", "status", "created_at"),)

    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    complainant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ComplaintStatus] = mapped_column(
        enum_type(ComplaintStatus), default=ComplaintStatus.NEW, nullable=False, index=True
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    handled_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    listing: Mapped[Listing | None] = relationship(lazy="joined")
    organization: Mapped["Organization | None"] = relationship(lazy="joined")  # noqa: F821
    complainant: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys=[complainant_id], lazy="joined"
    )
