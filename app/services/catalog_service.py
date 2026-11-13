from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache
from app.core.errors import AppError
from app.core.utils import slugify_text
from app.models.catalog import Category, CategoryAttribute
from app.models.enums import AttributeType, ListingType
from app.models.listing import Listing
from app.models.organization import Capability
from app.schemas.catalog import (
    AttributeCreate,
    AttributeUpdate,
    CategoryCreate,
    CategoryDetail,
    CategoryOut,
    CategoryUpdate,
)
from app.schemas.organization import CapabilityOut
from app.services.serializers import (
    category_detail,
    category_out,
)

CATALOG_CACHE_TTL = 300


async def load_categories(db: AsyncSession, *, include_inactive: bool = True) -> list[Category]:
    query = (
        select(Category)
        .options(selectinload(Category.attributes))
        .order_by(Category.sort_order, Category.name)
    )
    if not include_inactive:
        query = query.where(Category.is_active.is_(True))
    result = await db.execute(query)
    return list(result.scalars().unique().all())


def _category_depth(category: Category, by_id: dict[uuid.UUID, Category]) -> int:
    depth = 1
    current = category
    seen: set[uuid.UUID] = set()
    while current.parent_id:
        if current.id in seen:
            break
        seen.add(current.id)
        parent = by_id.get(current.parent_id)
        if parent is None:
            break
        depth += 1
        current = parent
    return depth


def _subtree_height(category: Category, children_map: dict[uuid.UUID | None, list[Category]]) -> int:
    children = children_map.get(category.id, [])
    if not children:
        return 1
    return 1 + max(_subtree_height(child, children_map) for child in children)


def _node(category: Category, children_map: dict[uuid.UUID | None, list[Category]]) -> CategoryOut:
    base = category_out(category)
    base.children = [_node(child, children_map) for child in children_map.get(category.id, [])]
    return base


async def category_tree(db: AsyncSession, *, include_inactive: bool = False) -> list[CategoryOut]:
    categories = await load_categories(db, include_inactive=include_inactive)
    children_map: dict[uuid.UUID | None, list[Category]] = {}
    for category in categories:
        children_map.setdefault(category.parent_id, []).append(category)
    return [_node(category, children_map) for category in children_map.get(None, [])]


async def get_category(db: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await db.scalar(
        select(Category)
        .where(Category.id == category_id)
        .options(selectinload(Category.attributes))
    )
    if category is None:
        raise AppError("Категория не найдена", status_code=404, code="category_not_found")
    return category


async def get_category_detail(db: AsyncSession, category_id: uuid.UUID) -> CategoryDetail:
    categories = await load_categories(db, include_inactive=True)
    by_id = {item.id: item for item in categories}
    category = by_id.get(category_id)
    if category is None:
        raise AppError("Категория не найдена", status_code=404, code="category_not_found")
    ancestors: list[Category] = []
    current = category
    seen: set[uuid.UUID] = set()
    while current.parent_id and current.id not in seen:
        seen.add(current.id)
        parent = by_id.get(current.parent_id)
        if parent is None:
            break
        ancestors.append(parent)
        current = parent
    ancestors.reverse()
    merged = _merge_attributes([*ancestors, category])
    return category_detail(
        category,
        ancestors=ancestors,
        inherited_attributes=merged,
    )


def _merge_attributes(categories: list[Category]) -> list[CategoryAttribute]:
    merged: dict[str, CategoryAttribute] = {}
    for category in categories:
        for attribute in category.attributes:
            merged[attribute.key] = attribute
    return sorted(merged.values(), key=lambda item: (item.sort_order, item.name))


async def merged_attributes(db: AsyncSession, category_id: uuid.UUID) -> list[CategoryAttribute]:
    categories = await load_categories(db, include_inactive=True)
    by_id = {item.id: item for item in categories}
    category = by_id.get(category_id)
    if category is None:
        raise AppError("Категория не найдена", status_code=404, code="category_not_found")
    chain: list[Category] = []
    current = category
    seen: set[uuid.UUID] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current)
        current = by_id.get(current.parent_id) if current.parent_id else None
    chain.reverse()
    return _merge_attributes(chain)


def _option_values(options: list[Any]) -> list[str]:
    values: list[str] = []
    for option in options or []:
        if isinstance(option, dict):
            value = option.get("value")
            if value is not None:
                values.append(str(value))
        else:
            values.append(str(option))
    return values


def _validate_one(attribute: CategoryAttribute, value: Any) -> tuple[Any, str | None]:
    attr_type = attribute.type.value if hasattr(attribute.type, "value") else str(attribute.type)
    if attr_type == AttributeType.STRING.value:
        if not isinstance(value, str):
            return value, "ожидается строка"
        if len(value) > 2000:
            return value, "строка длиннее 2000 символов"
        return value.strip(), None
    if attr_type == AttributeType.NUMBER.value:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return value, "ожидается число"
        return float(value), None
    if attr_type == AttributeType.BOOL.value:
        if not isinstance(value, bool):
            return value, "ожидается true/false"
        return value, None
    if attr_type == AttributeType.ENUM.value:
        allowed = _option_values(attribute.options or [])
        if str(value) not in allowed:
            return value, f"допустимые значения: {', '.join(allowed)}"
        return str(value), None
    if attr_type == AttributeType.MULTI_ENUM.value:
        if not isinstance(value, list):
            return value, "ожидается список значений"
        allowed = _option_values(attribute.options or [])
        normalized = [str(item) for item in value]
        invalid = [item for item in normalized if item not in allowed]
        if invalid:
            return value, f"недопустимые значения: {', '.join(invalid)}"
        return normalized, None
    if attr_type == AttributeType.RANGE.value:
        raw = value
        if isinstance(value, list) and len(value) == 2:
            raw = {"from": value[0], "to": value[1]}
        if not isinstance(raw, dict):
            return value, "ожидается объект {from, to} или [min, max]"
        start = raw.get("from", raw.get("min"))
        end = raw.get("to", raw.get("max"))
        if start is None and end is None:
            return value, "нужно указать from/to"
        if start is not None and (isinstance(start, bool) or not isinstance(start, (int, float))):
            return value, "from должен быть числом"
        if end is not None and (isinstance(end, bool) or not isinstance(end, (int, float))):
            return value, "to должен быть числом"
        if start is not None and end is not None and float(start) > float(end):
            return value, "from больше to"
        return {"from": start, "to": end}, None
    if attr_type == AttributeType.DATE.value:
        if isinstance(value, datetime):
            return value.isoformat(), None
        if isinstance(value, date):
            return value.isoformat(), None
        if not isinstance(value, str):
            return value, "ожидается дата ISO 8601"
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value, None
        except ValueError:
            return value, "некорректная дата ISO 8601"
    return value, "неизвестный тип атрибута"


async def validate_listing_attributes(
    db: AsyncSession,
    *,
    category_id: uuid.UUID,
    attributes: dict[str, Any] | None,
) -> dict[str, Any]:
    schema = await merged_attributes(db, category_id)
    attrs = attributes or {}
    if not isinstance(attrs, dict):
        raise AppError(
            "Атрибуты должны быть объектом", status_code=422, code="invalid_attributes"
        )
    known = {attribute.key for attribute in schema}
    unknown = sorted(set(attrs) - known)
    errors: dict[str, str] = {}
    normalized: dict[str, Any] = {}
    for attribute in schema:
        value = attrs.get(attribute.key)
        if value is None or value == "" or value == []:
            if attribute.is_required:
                errors[attribute.key] = "обязательное поле"
            continue
        coerced, error = _validate_one(attribute, value)
        if error:
            errors[attribute.key] = error
        else:
            normalized[attribute.key] = coerced
    if unknown or errors:
        details: dict[str, Any] = {}
        if unknown:
            details["unknown"] = unknown
        if errors:
            details["errors"] = errors
        raise AppError(
            "Атрибуты не соответствуют схеме категории",
            status_code=422,
            code="invalid_attributes",
            details=details,
        )
    return normalized


def allowed_types(category: Category) -> list[str]:
    if category.allowed_types:
        return list(category.allowed_types)
    return [item.value for item in ListingType]


async def descendant_ids(db: AsyncSession, category_id: uuid.UUID) -> list[uuid.UUID]:
    cache_key = f"catalog:descendants:{category_id}"
    cached = await cache.get_json(cache_key)
    if cached:
        return [uuid.UUID(item) for item in cached]
    categories = await load_categories(db, include_inactive=True)
    children_map: dict[uuid.UUID | None, list[Category]] = {}
    for category in categories:
        children_map.setdefault(category.parent_id, []).append(category)
    result: list[uuid.UUID] = []
    stack = [category_id]
    seen: set[uuid.UUID] = set()
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        result.append(current)
        stack.extend(child.id for child in children_map.get(current, []))
    await cache.set_json(cache_key, [str(item) for item in result], ttl=CATALOG_CACHE_TTL)
    return result


async def _invalidate_catalog_cache() -> None:
    await cache.delete_prefix("catalog:")


def _ensure_allowed_types(values: list[str]) -> list[str]:
    valid = {item.value for item in ListingType}
    unknown = [item for item in values if item not in valid]
    if unknown:
        raise AppError(
            "Недопустимые типы объявлений",
            status_code=422,
            code="invalid_listing_types",
            details={"unknown": unknown, "allowed": sorted(valid)},
        )
    return values


async def _ensure_slug_unique(
    db: AsyncSession, slug: str, *, exclude_id: uuid.UUID | None = None
) -> None:
    query = select(Category.id).where(Category.slug == slug)
    if exclude_id:
        query = query.where(Category.id != exclude_id)
    if await db.scalar(query):
        raise AppError("Категория с таким slug уже существует", status_code=409, code="slug_taken")


async def create_category(db: AsyncSession, data: CategoryCreate) -> Category:
    parent = None
    if data.parent_id:
        parent = await get_category(db, data.parent_id)
    categories = await load_categories(db, include_inactive=True)
    by_id = {item.id: item for item in categories}
    depth = 1
    if parent:
        depth = _category_depth(parent, by_id) + 1
    if depth > 3:
        raise AppError(
            "Дерево категорий поддерживает максимум 3 уровня",
            status_code=422,
            code="category_depth_exceeded",
        )
    slug = slugify_text(data.slug or data.name, fallback="category")
    await _ensure_slug_unique(db, slug)
    category = Category(
        parent_id=data.parent_id,
        slug=slug,
        name=data.name.strip(),
        description=data.description,
        sort_order=data.sort_order,
        is_active=data.is_active,
        allowed_types=_ensure_allowed_types(data.allowed_types),
    )
    db.add(category)
    await db.commit()
    return await get_category(db, category.id)


async def update_category(
    db: AsyncSession, category_id: uuid.UUID, data: CategoryUpdate
) -> Category:
    category = await get_category(db, category_id)
    categories = await load_categories(db, include_inactive=True)
    by_id = {item.id: item for item in categories}
    children_map: dict[uuid.UUID | None, list[Category]] = {}
    for item in categories:
        children_map.setdefault(item.parent_id, []).append(item)

    if data.parent_id is not None:
        if data.parent_id == category.id:
            raise AppError(
                "Категория не может быть родителем сама себе",
                status_code=422,
                code="category_cycle",
            )
        new_parent = by_id.get(data.parent_id)
        if new_parent is None:
            raise AppError("Родительская категория не найдена", status_code=404, code="category_not_found")
        current = new_parent
        seen: set[uuid.UUID] = set()
        while current is not None and current.id not in seen:
            if current.id == category.id:
                raise AppError(
                    "Нельзя переместить категорию внутрь её потомка",
                    status_code=422,
                    code="category_cycle",
                )
            seen.add(current.id)
            current = by_id.get(current.parent_id) if current.parent_id else None
        new_depth = _category_depth(new_parent, by_id) + 1
        height = _subtree_height(category, children_map)
        if new_depth + height - 1 > 3:
            raise AppError(
                "Дерево категорий поддерживает максимум 3 уровня",
                status_code=422,
                code="category_depth_exceeded",
            )
        category.parent_id = data.parent_id

    if data.name is not None:
        category.name = data.name.strip()
    if data.description is not None:
        category.description = data.description
    if data.sort_order is not None:
        category.sort_order = data.sort_order
    if data.is_active is not None:
        category.is_active = data.is_active
    if data.allowed_types is not None:
        category.allowed_types = _ensure_allowed_types(data.allowed_types)
    if data.slug is not None and data.slug != category.slug:
        slug = slugify_text(data.slug, fallback="category")
        await _ensure_slug_unique(db, slug, exclude_id=category.id)
        category.slug = slug
    await db.commit()
    await _invalidate_catalog_cache()
    return await get_category(db, category.id)


async def delete_category(db: AsyncSession, category_id: uuid.UUID) -> None:
    category = await get_category(db, category_id)
    child_count = await db.scalar(
        select(func.count(Category.id)).where(Category.parent_id == category_id)
    )
    if child_count:
        raise AppError(
            "Сначала удалите или переместите дочерние категории",
            status_code=409,
            code="category_has_children",
        )
    listing_count = await db.scalar(
        select(func.count(Listing.id)).where(Listing.category_id == category_id)
    )
    if listing_count:
        raise AppError(
            "Нельзя удалить категорию, в которой есть объявления",
            status_code=409,
            code="category_has_listings",
        )
    await db.delete(category)
    await db.commit()
    await _invalidate_catalog_cache()


async def create_attribute(
    db: AsyncSession, category_id: uuid.UUID, data: AttributeCreate
) -> CategoryAttribute:
    await get_category(db, category_id)
    try:
        attr_type = AttributeType(data.type)
    except ValueError as exc:
        raise AppError("Недопустимый тип атрибута", status_code=422, code="invalid_attribute_type") from exc
    if attr_type in (AttributeType.ENUM, AttributeType.MULTI_ENUM) and not data.options:
        raise AppError(
            "Для enum/multi_enum нужны варианты значений",
            status_code=422,
            code="attribute_options_required",
        )
    existing = await db.scalar(
        select(CategoryAttribute.id).where(
            CategoryAttribute.category_id == category_id,
            CategoryAttribute.key == data.key,
        )
    )
    if existing:
        raise AppError("Атрибут с таким ключом уже существует", status_code=409, code="attribute_exists")
    attribute = CategoryAttribute(
        category_id=category_id,
        key=data.key,
        name=data.name,
        type=attr_type,
        unit=data.unit,
        is_required=data.is_required,
        is_filterable=data.is_filterable,
        options=data.options,
        sort_order=data.sort_order,
    )
    db.add(attribute)
    await db.commit()
    await db.refresh(attribute)
    await _invalidate_catalog_cache()
    return attribute


async def update_attribute(
    db: AsyncSession, attribute_id: uuid.UUID, data: AttributeUpdate
) -> CategoryAttribute:
    attribute = await db.get(CategoryAttribute, attribute_id)
    if attribute is None:
        raise AppError("Атрибут не найден", status_code=404, code="attribute_not_found")
    if data.key is not None and data.key != attribute.key:
        duplicate = await db.scalar(
            select(CategoryAttribute.id).where(
                CategoryAttribute.category_id == attribute.category_id,
                CategoryAttribute.key == data.key,
                CategoryAttribute.id != attribute.id,
            )
        )
        if duplicate:
            raise AppError("Атрибут с таким ключом уже существует", status_code=409, code="attribute_exists")
        attribute.key = data.key
    if data.name is not None:
        attribute.name = data.name
    if data.type is not None:
        try:
            attribute.type = AttributeType(data.type)
        except ValueError as exc:
            raise AppError("Недопустимый тип атрибута", status_code=422, code="invalid_attribute_type") from exc
    if data.unit is not None:
        attribute.unit = data.unit
    if data.is_required is not None:
        attribute.is_required = data.is_required
    if data.is_filterable is not None:
        attribute.is_filterable = data.is_filterable
    if data.options is not None:
        attribute.options = data.options
    if data.sort_order is not None:
        attribute.sort_order = data.sort_order
    if attribute.type in (AttributeType.ENUM, AttributeType.MULTI_ENUM) and not attribute.options:
        raise AppError(
            "Для enum/multi_enum нужны варианты значений",
            status_code=422,
            code="attribute_options_required",
        )
    await db.commit()
    await db.refresh(attribute)
    await _invalidate_catalog_cache()
    return attribute


async def delete_attribute(db: AsyncSession, attribute_id: uuid.UUID) -> None:
    attribute = await db.get(CategoryAttribute, attribute_id)
    if attribute is None:
        raise AppError("Атрибут не найден", status_code=404, code="attribute_not_found")
    await db.delete(attribute)
    await db.commit()
    await _invalidate_catalog_cache()


async def list_capabilities(db: AsyncSession) -> list[CapabilityOut]:
    result = await db.execute(select(Capability).order_by(Capability.name))
    return [
        CapabilityOut(
            code=item.code,
            name=item.name,
            param_schema=item.param_schema or {},
            is_active=item.is_active,
        )
        for item in result.scalars().all()
    ]
