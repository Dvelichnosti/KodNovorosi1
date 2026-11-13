from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import JSON_TYPE, Base, TimestampMixin
from app.models.base import UUIDPrimaryKeyMixin, enum_type
from app.models.enums import AttributeType, ListingType


class Category(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "categories"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    allowed_types: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)

    parent: Mapped[Category | None] = relationship(
        remote_side="Category.id",
        back_populates="children",
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="Category.sort_order",
    )
    attributes: Mapped[list[CategoryAttribute]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="CategoryAttribute.sort_order",
        lazy="selectin",
    )


class CategoryAttribute(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "category_attributes"
    __table_args__ = (
        UniqueConstraint("category_id", "key", name="uq_category_attributes_category_key"),
        Index("ix_category_attributes_filterable", "category_id", "is_filterable"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[AttributeType] = mapped_column(enum_type(AttributeType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    is_required: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_filterable: Mapped[bool] = mapped_column(default=True, nullable=False)
    options: Mapped[list[Any]] = mapped_column(JSON_TYPE, default=list)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)

    category: Mapped[Category] = relationship(back_populates="attributes")


def allowed_types_for_category(category: Category) -> list[str]:
    if category.allowed_types:
        return list(category.allowed_types)
    return [item.value for item in ListingType]
