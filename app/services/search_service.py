from __future__ import annotations

import uuid

from sqlalchemy import Numeric, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import utcnow
from app.models.enums import ListingStatus, PromotionType
from app.models.listing import Favorite, Listing, ListingPromotion
from app.models.user import User
from app.services import catalog_service


def _dialect_name(db: AsyncSession) -> str:
    try:
        bind = db.get_bind()
        return bind.dialect.name
    except Exception:
        return "postgresql"


def _attribute_value(expression):
    return expression.as_string()


def _apply_attribute_filter(query, key: str, value: str):
    column = Listing.attributes[key]
    return query.where(_attribute_value(column) == value)


def _apply_attribute_range(query, key: str, minimum: str | None, maximum: str | None):
    column = Listing.attributes[key]
    if minimum is not None:
        query = query.where(cast(_attribute_value(column), Numeric) >= float(minimum))
    if maximum is not None:
        query = query.where(cast(_attribute_value(column), Numeric) <= float(maximum))
    return query


async def search_listings(
    db: AsyncSession,
    viewer: User | None,
    *,
    q: str | None = None,
    category_id: uuid.UUID | None = None,
    listing_type: str | None = None,
    region: str | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    organization_id: uuid.UUID | None = None,
    sort: str = "date",
    attr_filters: dict[str, str] | None = None,
    attr_ranges: dict[str, tuple[str | None, str | None]] | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Listing], int]:
    dialect = _dialect_name(db)
    now = utcnow()
    query = select(Listing).where(
        Listing.status == ListingStatus.ACTIVE,
        Listing.deleted_at.is_(None),
        or_(Listing.expires_at.is_(None), Listing.expires_at > now),
    )
    if category_id:
        ids = await catalog_service.descendant_ids(db, category_id)
        query = query.where(Listing.category_id.in_(ids))
    if listing_type:
        query = query.where(Listing.type == listing_type)
    if region:
        query = query.where(Listing.region == region)
    if organization_id:
        query = query.where(Listing.organization_id == organization_id)
    if price_min is not None:
        query = query.where(Listing.price.is_not(None), Listing.price >= price_min)
    if price_max is not None:
        query = query.where(Listing.price.is_not(None), Listing.price <= price_max)

    for key, value in (attr_filters or {}).items():
        query = _apply_attribute_filter(query, key, value)
    for key, (minimum, maximum) in (attr_ranges or {}).items():
        query = _apply_attribute_range(query, key, minimum, maximum)

    relevance = None
    if q:
        term = q.strip()
        if term:
            if dialect == "postgresql":
                vector = func.to_tsvector(
                    "russian",
                    Listing.title + " " + Listing.description,
                )
                ts_query = func.plainto_tsquery("russian", term)
                query = query.where(vector.op("@@")(ts_query))
                relevance = func.ts_rank(vector, ts_query)
            else:
                pattern = f"%{term}%"
                query = query.where(
                    or_(Listing.title.ilike(pattern), Listing.description.ilike(pattern))
                )

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0

    top_exists = (
        select(ListingPromotion.id)
        .where(
            ListingPromotion.listing_id == Listing.id,
            ListingPromotion.type == PromotionType.TOP,
            ListingPromotion.starts_at <= now,
            or_(ListingPromotion.ends_at.is_(None), ListingPromotion.ends_at > now),
        )
        .exists()
    )

    if sort == "price_asc":
        query = query.order_by(Listing.price.asc().nullslast(), Listing.published_at.desc())
    elif sort == "price_desc":
        query = query.order_by(Listing.price.desc().nullslast(), Listing.published_at.desc())
    elif sort == "relevance" and relevance is not None:
        query = query.order_by(
            relevance.desc(),
            top_exists.desc(),
            Listing.bumped_at.desc().nullslast(),
            Listing.published_at.desc(),
        )
    else:
        query = query.order_by(
            top_exists.desc(),
            Listing.bumped_at.desc().nullslast(),
            Listing.published_at.desc(),
            Listing.created_at.desc(),
        )

    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    listings = list(result.scalars().unique().all())
    return listings, int(total)


async def favorite_ids(
    db: AsyncSession, viewer: User | None, listing_ids: list[uuid.UUID]
) -> set[uuid.UUID]:
    if viewer is None or not listing_ids:
        return set()
    result = await db.execute(
        select(Favorite.listing_id).where(
            Favorite.user_id == viewer.id,
            Favorite.listing_id.in_(listing_ids),
        )
    )
    return set(result.scalars().all())
