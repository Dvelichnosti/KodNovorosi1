from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.permissions import PLATFORM_ROLE_TEMPLATES
from app.core.utils import normalize_phone, slugify_text
from app.models.billing import Plan
from app.models.catalog import Category, CategoryAttribute
from app.models.enums import AttributeType
from app.models.organization import Capability
from app.models.system import PlatformSetting
from app.models.user import PlatformRole, User, UserPlatformRole
from app.seed_data import (
    ALLOWED_TYPES,
    CATEGORY_ATTRIBUTES,
    CATEGORY_TREE,
    PLANS,
    ROOT_SLUGS,
    SETTINGS,
)

logger = logging.getLogger(__name__)


async def seed_platform_roles(db: AsyncSession) -> dict[str, PlatformRole]:
    roles: dict[str, PlatformRole] = {}
    for template in PLATFORM_ROLE_TEMPLATES:
        role = await db.scalar(select(PlatformRole).where(PlatformRole.code == template["code"]))
        if role is None:
            role = PlatformRole(
                code=template["code"],
                name=template["name"],
                permissions=list(template["permissions"]),
                is_system=template["is_system"],
            )
            db.add(role)
        else:
            role.name = template["name"]
            role.permissions = list(template["permissions"])
            role.is_system = template["is_system"]
        roles[role.code] = role
    await db.flush()
    return roles


async def seed_capabilities(db: AsyncSession) -> None:
    from app.core.reference import DEFAULT_CAPABILITIES

    for item in DEFAULT_CAPABILITIES:
        capability = await db.get(Capability, item["code"])
        if capability is None:
            capability = Capability(code=item["code"])
            db.add(capability)
        capability.name = item["name"]
        capability.param_schema = item["param_schema"]
        capability.is_active = True
    await db.flush()


async def seed_plans(db: AsyncSession) -> None:
    for item in PLANS:
        plan = await db.scalar(select(Plan).where(Plan.code == item["code"]))
        if plan is None:
            plan = Plan(code=item["code"])
            db.add(plan)
        plan.name = item["name"]
        plan.max_active_listings = item["max_active_listings"]
        plan.price = Decimal(str(item["price"]))
        plan.features = item["features"]
        plan.description = item["description"]
        plan.is_active = True
        plan.sort_order = item["sort_order"]
    await db.flush()


async def seed_categories(db: AsyncSession) -> None:
    used_slugs: set[str] = set()
    for root_order, (root_name, children) in enumerate(CATEGORY_TREE.items(), start=1):
        root_slug = ROOT_SLUGS[root_name]
        used_slugs.add(root_slug)
        root = await db.scalar(select(Category).where(Category.slug == root_slug))
        if root is None:
            root = Category(slug=root_slug, name=root_name)
            db.add(root)
        root.name = root_name
        root.parent_id = None
        root.sort_order = root_order
        root.is_active = True
        root.allowed_types = ALLOWED_TYPES.get(root_slug, [])
        await db.flush()

        for child_order, child_name in enumerate(children, start=1):
            child_slug = f"{root_slug}-{slugify_text(child_name)}"
            if child_slug in used_slugs:
                child_slug = f"{child_slug}-{child_order}"
            used_slugs.add(child_slug)
            child = await db.scalar(select(Category).where(Category.slug == child_slug))
            if child is None:
                child = Category(slug=child_slug, name=child_name)
                db.add(child)
            child.name = child_name
            child.parent_id = root.id
            child.sort_order = child_order
            child.is_active = True
            child.allowed_types = ALLOWED_TYPES.get(root_slug, [])
        await db.flush()

    # Attributes are attached to root categories and inherited by children.
    for root_slug, attributes in CATEGORY_ATTRIBUTES.items():
        category = await db.scalar(select(Category).where(Category.slug == root_slug))
        if category is None:
            continue
        for item in attributes:
            attribute = await db.scalar(
                select(CategoryAttribute).where(
                    CategoryAttribute.category_id == category.id,
                    CategoryAttribute.key == item["key"],
                )
            )
            if attribute is None:
                attribute = CategoryAttribute(
                    category_id=category.id,
                    key=item["key"],
                    name=item["name"],
                    type=AttributeType(item["type"]),
                )
                db.add(attribute)
            attribute.name = item["name"]
            attribute.type = AttributeType(item["type"])
            attribute.unit = item.get("unit")
            attribute.is_required = bool(item.get("is_required", False))
            attribute.is_filterable = bool(item.get("is_filterable", True))
            attribute.options = item.get("options", [])
            attribute.sort_order = int(item.get("sort_order", 0))
    await db.flush()


async def seed_settings(db: AsyncSession) -> None:
    for item in SETTINGS:
        setting = await db.get(PlatformSetting, item["key"])
        if setting is None:
            setting = PlatformSetting(key=item["key"])
            db.add(setting)
        setting.value = item["value"]
        setting.description = item["description"]
    await db.flush()


async def seed_superadmin(db: AsyncSession, roles: dict[str, PlatformRole]) -> None:
    if not settings.superadmin_telegram_id:
        return
    user = await db.scalar(
        select(User).where(User.telegram_id == settings.superadmin_telegram_id)
    )
    if user is None:
        user = User(
            telegram_id=settings.superadmin_telegram_id,
            phone=normalize_phone(settings.superadmin_phone),
            first_name="Superadmin",
            notification_settings={},
        )
        db.add(user)
        await db.flush()
    link = await db.scalar(
        select(UserPlatformRole).where(
            UserPlatformRole.user_id == user.id,
            UserPlatformRole.role_id == roles["superadmin"].id,
        )
    )
    if link is None:
        db.add(
            UserPlatformRole(
                user_id=user.id,
                role_id=roles["superadmin"].id,
            )
        )
    await db.flush()
    logger.info("Superadmin seeded for telegram_id=%s", settings.superadmin_telegram_id)


async def seed_all(db: AsyncSession) -> None:
    roles = await seed_platform_roles(db)
    await seed_capabilities(db)
    await seed_plans(db)
    await seed_categories(db)
    await seed_settings(db)
    await seed_superadmin(db, roles)
    await db.commit()


async def main() -> None:
    from app.core.database import SessionLocal, engine

    async with SessionLocal() as session:
        await seed_all(session)
    await engine.dispose()
    logger.info("Seed completed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
