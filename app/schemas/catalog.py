from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AttributeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    key: str
    name: str
    type: str
    unit: str | None = None
    is_required: bool
    is_filterable: bool
    options: list[Any] = Field(default_factory=list)
    sort_order: int = 0


class CategoryShort(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    parent_id: uuid.UUID | None = None


class CategoryOut(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None = None
    slug: str
    name: str
    description: str | None = None
    sort_order: int
    is_active: bool
    allowed_types: list[str] = Field(default_factory=list)
    attributes: list[AttributeOut] = Field(default_factory=list)
    children: list["CategoryOut"] = Field(default_factory=list)


class CategoryDetail(CategoryOut):
    ancestors: list[CategoryShort] = Field(default_factory=list)
    inherited_attributes: list[AttributeOut] = Field(default_factory=list)


class CategoryCreate(BaseModel):
    parent_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, max_length=160)
    name: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0
    is_active: bool = True
    allowed_types: list[str] = Field(default_factory=list)


class CategoryUpdate(BaseModel):
    parent_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, max_length=160)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = None
    is_active: bool | None = None
    allowed_types: list[str] | None = None


class AttributeCreate(BaseModel):
    key: str = Field(min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2, max_length=128)
    type: str = Field(pattern="^(string|number|enum|multi_enum|bool|range|date)$")
    unit: str | None = Field(default=None, max_length=32)
    is_required: bool = False
    is_filterable: bool = True
    options: list[Any] = Field(default_factory=list)
    sort_order: int = 0


class AttributeUpdate(BaseModel):
    key: str | None = Field(default=None, min_length=1, max_length=64, pattern="^[a-z][a-z0-9_]*$")
    name: str | None = Field(default=None, min_length=2, max_length=128)
    type: str | None = Field(default=None, pattern="^(string|number|enum|multi_enum|bool|range|date)$")
    unit: str | None = Field(default=None, max_length=32)
    is_required: bool | None = None
    is_filterable: bool | None = None
    options: list[Any] | None = None
    sort_order: int | None = None


CategoryOut.model_rebuild()
