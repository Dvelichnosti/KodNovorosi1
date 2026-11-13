from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.utils import client_ip
from app.schemas.catalog import (
    AttributeCreate,
    AttributeOut,
    AttributeUpdate,
    CategoryCreate,
    CategoryDetail,
    CategoryOut,
    CategoryUpdate,
)
from app.schemas.common import Message
from app.services import catalog_service
from app.services.serializers import attribute_out, category_out

router = APIRouter(prefix="/catalog", tags=["admin: catalog"])


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> list[CategoryOut]:
    return await catalog_service.category_tree(db, include_inactive=True)


@router.get("/categories/{category_id}", response_model=CategoryDetail)
async def get_category(
    category_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> CategoryDetail:
    return await catalog_service.get_category_detail(db, category_id)


@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(
    data: CategoryCreate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> CategoryOut:
    category = await catalog_service.create_category(db, data)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.category_create",
        entity_type="category",
        entity_id=category.id,
        payload={"name": category.name, "slug": category.slug},
        ip=client_ip(request),
    )
    await db.commit()
    return category_out(category)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> CategoryOut:
    category = await catalog_service.update_category(db, category_id, data)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.category_update",
        entity_type="category",
        entity_id=category.id,
        payload=data.model_dump(exclude_unset=True),
        ip=client_ip(request),
    )
    await db.commit()
    return category_out(category)


@router.delete("/categories/{category_id}", response_model=Message)
async def delete_category(
    category_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> Message:
    await catalog_service.delete_category(db, category_id)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.category_delete",
        entity_type="category",
        entity_id=category_id,
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Категория удалена")


@router.post("/categories/{category_id}/attributes", response_model=AttributeOut, status_code=201)
async def create_attribute(
    category_id: uuid.UUID,
    data: AttributeCreate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> AttributeOut:
    attribute = await catalog_service.create_attribute(db, category_id, data)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.attribute_create",
        entity_type="category_attribute",
        entity_id=attribute.id,
        payload={"key": attribute.key, "category_id": str(category_id)},
        ip=client_ip(request),
    )
    await db.commit()
    return attribute_out(attribute)


@router.patch("/attributes/{attribute_id}", response_model=AttributeOut)
async def update_attribute(
    attribute_id: uuid.UUID,
    data: AttributeUpdate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> AttributeOut:
    attribute = await catalog_service.update_attribute(db, attribute_id, data)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.attribute_update",
        entity_type="category_attribute",
        entity_id=attribute.id,
        payload=data.model_dump(exclude_unset=True),
        ip=client_ip(request),
    )
    await db.commit()
    return attribute_out(attribute)


@router.delete("/attributes/{attribute_id}", response_model=Message)
async def delete_attribute(
    attribute_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("catalog.manage")),
    db: DB = None,
) -> Message:
    await catalog_service.delete_attribute(db, attribute_id)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="catalog.attribute_delete",
        entity_type="category_attribute",
        entity_id=attribute_id,
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Атрибут удалён")
