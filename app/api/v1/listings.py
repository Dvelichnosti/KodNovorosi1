from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import DB, AuthContext, get_auth, get_optional_user
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import enforce_rate_limit
from app.core.utils import client_ip
from app.models.enums import ListingStatus, ListingType, Region
from app.models.user import User
from app.schemas.common import Message, Page
from app.schemas.listing import (
    ComplaintCreate,
    ComplaintOut,
    ListingCreate,
    ListingOut,
    ListingStatsOut,
    ListingUpdate,
)
from app.services import listing_service, search_service
from app.services.serializers import complaint_out, listing_out

router = APIRouter(prefix="/listings", tags=["listings"])


def _parse_attribute_filters(request: Request) -> tuple[dict[str, str], dict[str, tuple[str | None, str | None]]]:
    filters: dict[str, str] = {}
    ranges: dict[str, tuple[str | None, str | None]] = {}
    for key, value in request.query_params.multi_items():
        if not key.startswith("attr."):
            continue
        rest = key[5:]
        if rest.endswith(".min"):
            name = rest[:-4]
            current = ranges.get(name, (None, None))
            ranges[name] = (value, current[1])
        elif rest.endswith(".max"):
            name = rest[:-4]
            current = ranges.get(name, (None, None))
            ranges[name] = (current[0], value)
        elif rest:
            filters[rest] = value
    return filters, ranges


@router.get("", response_model=Page[ListingOut])
async def search_listings(
    request: Request,
    q: str | None = Query(default=None, max_length=200),
    category_id: uuid.UUID | None = Query(default=None),
    type: ListingType | None = Query(default=None),
    region: Region | None = Query(default=None),
    price_min: float | None = Query(default=None, ge=0),
    price_max: float | None = Query(default=None, ge=0),
    organization_id: uuid.UUID | None = Query(default=None),
    sort: str = Query(default="date", pattern="^(date|price_asc|price_desc|relevance)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    viewer: User | None = Depends(get_optional_user),
    db: DB = None,
) -> Page[ListingOut]:
    attr_filters, attr_ranges = _parse_attribute_filters(request)
    listings, total = await search_service.search_listings(
        db,
        viewer,
        q=q,
        category_id=category_id,
        listing_type=type.value if type else None,
        region=region.value if region else None,
        price_min=price_min,
        price_max=price_max,
        organization_id=organization_id,
        sort=sort,
        attr_filters=attr_filters,
        attr_ranges=attr_ranges,
        page=page,
        per_page=per_page,
    )
    favorites = await search_service.favorite_ids(
        db, viewer, [item.id for item in listings]
    )
    items = [
        listing_out(
            item,
            contacts_visible=viewer is not None,
            is_favorite=item.id in favorites,
        )
        for item in listings
    ]
    return Page.build(items, total, page, per_page)


@router.get("/mine", response_model=Page[ListingOut])
async def my_listings(
    status_filter: ListingStatus | None = Query(default=None, alias="status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Page[ListingOut]:
    listings, total = await listing_service.list_my_listings(
        db,
        auth.user,
        status=status_filter.value if status_filter else None,
        page=page,
        per_page=per_page,
    )
    items = [listing_out(item, contacts_visible=True) for item in listings]
    return Page.build(items, total, page, per_page)


@router.get("/{listing_id}", response_model=ListingOut)
async def get_listing(
    listing_id: uuid.UUID,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.get_listing(db, listing_id)
    if not await listing_service.can_view_listing(db, viewer, listing):
        raise AppError("Объявление не найдено", status_code=404, code="listing_not_found")
    await listing_service.record_view(
        db,
        listing.id,
        user_id=viewer.id if viewer else None,
        ip=client_ip(request),
    )
    favorite = (
        await listing_service.is_favorite(db, viewer.id, listing.id) if viewer else False
    )
    return listing_out(
        listing,
        contacts_visible=viewer is not None,
        is_favorite=favorite,
    )


@router.post("", response_model=ListingOut, status_code=status.HTTP_201_CREATED)
async def create_listing(
    data: ListingCreate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.create_listing(db, auth.user, data)
    return listing_out(listing, contacts_visible=True)


@router.patch("/{listing_id}", response_model=ListingOut)
async def update_listing(
    listing_id: uuid.UUID,
    data: ListingUpdate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.update_listing(db, auth.user, listing_id, data)
    return listing_out(listing, contacts_visible=True)


@router.delete("/{listing_id}", response_model=Message)
async def delete_listing(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await listing_service.delete_listing(db, auth.user, listing_id)
    return Message(message="Объявление удалено")


@router.post("/{listing_id}/submit", response_model=ListingOut)
async def submit_listing(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.submit_listing(db, auth.user, listing_id)
    return listing_out(listing, contacts_visible=True)


@router.post("/{listing_id}/archive", response_model=ListingOut)
async def archive_listing(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ListingOut:
    listing = await listing_service.archive_listing(db, auth.user, listing_id)
    return listing_out(listing, contacts_visible=True)


@router.get("/{listing_id}/stats", response_model=ListingStatsOut)
async def listing_stats(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ListingStatsOut:
    data = await listing_service.get_listing_stats(db, auth.user, listing_id)
    return ListingStatsOut(**data)


@router.post("/{listing_id}/favorite", response_model=Message)
async def add_favorite(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await listing_service.add_favorite(db, auth.user, listing_id)
    return Message(message="Добавлено в избранное")


@router.delete("/{listing_id}/favorite", response_model=Message)
async def remove_favorite(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await listing_service.remove_favorite(db, auth.user, listing_id)
    return Message(message="Удалено из избранного")


@router.post(
    "/{listing_id}/complaints",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_complaint(
    listing_id: uuid.UUID,
    data: ComplaintCreate,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> ComplaintOut:
    await enforce_rate_limit(
        f"complaint:{auth.user.id}",
        settings.complaint_rate_limit,
        settings.complaint_rate_window,
    )
    complaint = await listing_service.create_complaint(db, auth.user, listing_id, data)
    return complaint_out(complaint)


@router.post("/{listing_id}/bump", response_model=Message)
async def self_bump(
    listing_id: uuid.UUID,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    if not settings.promotions_self_service:
        raise AppError(
            "Самостоятельное продвижение пока недоступно. Обратитесь к администратору.",
            status_code=403,
            code="promotions_disabled",
        )
    listing = await listing_service.get_listing(db, listing_id)
    await listing_service.require_listing_permission(
        db, auth.user, listing, "listing.promote"
    )
    await listing_service.promote_listing(
        db, auth.user, listing.id, promotion_type="bump"
    )
    return Message(message="Объявление поднято")
