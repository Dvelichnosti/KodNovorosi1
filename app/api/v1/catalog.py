from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DB
from app.schemas.catalog import CategoryDetail, CategoryOut
from app.schemas.organization import CapabilityOut
from app.services import catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/categories", response_model=list[CategoryOut])
async def categories(db: DB) -> list[CategoryOut]:
    return await catalog_service.category_tree(db, include_inactive=False)


@router.get("/categories/{category_id}", response_model=CategoryDetail)
async def category(category_id: uuid.UUID, db: DB) -> CategoryDetail:
    return await catalog_service.get_category_detail(db, category_id)


@router.get("/capabilities", response_model=list[CapabilityOut])
async def capabilities(db: DB) -> list[CapabilityOut]:
    return await catalog_service.list_capabilities(db)
