from __future__ import annotations

from math import ceil
from typing import Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: object | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Message(BaseModel):
    message: str


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, per_page: int) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=ceil(total / per_page) if per_page else 0,
        )


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)


def pagination_params(
    page: int = Query(1, ge=1, description="Номер страницы"),
    per_page: int = Query(20, ge=1, le=100, description="Размер страницы"),
) -> PageParams:
    return PageParams(page=page, per_page=per_page)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
