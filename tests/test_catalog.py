from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.errors import AppError
from app.models.catalog import Category
from app.schemas.catalog import CategoryCreate
from app.services import catalog_service


@pytest.mark.asyncio
async def test_category_tree_is_limited_to_three_levels(seeded):
    db = seeded
    root = await catalog_service.create_category(db, CategoryCreate(name="Тестовая категория"))
    child = await catalog_service.create_category(
        db, CategoryCreate(name="Второй уровень", parent_id=root.id)
    )
    grandchild = await catalog_service.create_category(
        db, CategoryCreate(name="Третий уровень", parent_id=child.id)
    )
    with pytest.raises(AppError) as exc:
        await catalog_service.create_category(
            db, CategoryCreate(name="Четвёртый уровень", parent_id=grandchild.id)
        )
    assert exc.value.code == "category_depth_exceeded"


@pytest.mark.asyncio
async def test_child_inherits_required_attributes(seeded):
    db = seeded
    root = await db.scalar(select(Category).where(Category.slug == "oborudovanie"))
    assert root is not None
    child = await db.scalar(
        select(Category).where(
            Category.parent_id == root.id,
            Category.slug == "oborudovanie-proizvodstvennoe",
        )
    )
    assert child is not None

    merged = await catalog_service.merged_attributes(db, child.id)
    assert any(item.key == "condition" and item.is_required for item in merged)

    with pytest.raises(AppError) as exc:
        await catalog_service.validate_listing_attributes(
            db, category_id=child.id, attributes={}
        )
    assert exc.value.code == "invalid_attributes"
    assert "condition" in (exc.value.details or {}).get("errors", {})

    normalized = await catalog_service.validate_listing_attributes(
        db, category_id=child.id, attributes={"condition": "used", "year": 2020}
    )
    assert normalized == {"condition": "used", "year": 2020.0}


@pytest.mark.asyncio
async def test_unknown_attribute_is_rejected(seeded):
    db = seeded
    root = await db.scalar(select(Category).where(Category.slug == "oborudovanie"))
    with pytest.raises(AppError) as exc:
        await catalog_service.validate_listing_attributes(
            db,
            category_id=root.id,
            attributes={"condition": "new", "unknown_key": "x"},
        )
    assert exc.value.code == "invalid_attributes"
    assert "unknown_key" in (exc.value.details or {}).get("unknown", [])
