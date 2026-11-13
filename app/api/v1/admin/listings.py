from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.utils import client_ip
from app.models.enums import ListingStatus
from app.models.listing import Listing
from app.schemas.common import Message, Page
from app.schemas.listing import (
    ListingOut,
    ModerationBlockIn,
    ModerationRejectIn,
    PromotionCreateIn,
    PromotionOut,
)
from app.services import listing_service
from app.services.serializers import listing_out

router = APIRouter(prefix="/listings", tags=["admin: listings"])


@router.get("", response_model=Page[ListingOut])
async def list_listings(
    q: str | None = Query(default=None, max_length=200),
    status_filter: ListingStatus | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> Page[ListingOut]:
    query = select(Listing).where(Listing.deleted_at.is_(None))
    if status_filter:
        query = query.where(Listing.status == status_filter)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(Listing.title.ilike(pattern), Listing.description.ilike(pattern))
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(Listing.submitted_at.asc().nullslast(), Listing.created_at.asc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    listings = list(result.scalars().unique().all())
    items = [listing_out(item, contacts_visible=True) for item in listings]
    return Page.build(items, int(total), page, per_page)


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.get_listing(db, listing_id)
    return listing_out(listing, contacts_visible=True)


@router.post("/{listing_id}/approve", response_model=ListingOut)
async def approve_listing(
    listing_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.moderate_listing(
        db, auth.user, listing_id, decision="approve"
    )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="listing.approve",
        entity_type="listing",
        entity_id=listing.id,
        ip=client_ip(request),
    )
    await db.commit()
    return listing_out(listing, contacts_visible=True)


@router.post("/{listing_id}/reject", response_model=ListingOut)
async def reject_listing(
    listing_id: uuid.UUID,
    data: ModerationRejectIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.moderate_listing(
        db, auth.user, listing_id, decision="reject", reason=data.reason
    )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="listing.reject",
        entity_type="listing",
        entity_id=listing.id,
        payload={"reason": data.reason},
        ip=client_ip(request),
    )
    await db.commit()
    return listing_out(listing, contacts_visible=True)


@router.post("/{listing_id}/block", response_model=ListingOut)
async def block_listing(
    listing_id: uuid.UUID,
    data: ModerationBlockIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.moderate_listing(
        db, auth.user, listing_id, decision="block", reason=data.reason
    )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="listing.block",
        entity_type="listing",
        entity_id=listing.id,
        payload={"reason": data.reason},
        ip=client_ip(request),
    )
    await db.commit()
    return listing_out(listing, contacts_visible=True)


@router.post("/{listing_id}/promote", response_model=PromotionOut)
async def promote_listing(
    listing_id: uuid.UUID,
    data: PromotionCreateIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> PromotionOut:
    promotion = await listing_service.promote_listing(
        db,
        auth.user,
        listing_id,
        promotion_type=data.type,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
    )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="listing.promote",
        entity_type="listing",
        entity_id=listing_id,
        payload={"type": data.type, "promotion_id": str(promotion.id)},
        ip=client_ip(request),
    )
    await db.commit()
    return PromotionOut(
        id=promotion.id,
        type=promotion.type.value
        if hasattr(promotion.type, "value")
        else str(promotion.type),
        starts_at=promotion.starts_at,
        ends_at=promotion.ends_at,
    )


@router.delete("/{listing_id}/promotions/{promotion_id}", response_model=Message)
async def remove_promotion(
    listing_id: uuid.UUID,
    promotion_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("listings.moderate")),
    db: DB = None,
) -> Message:
    await listing_service.remove_promotion(db, listing_id, promotion_id)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="listing.promotion_remove",
        entity_type="listing",
        entity_id=listing_id,
        payload={"promotion_id": str(promotion_id)},
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Продвижение удалено")
