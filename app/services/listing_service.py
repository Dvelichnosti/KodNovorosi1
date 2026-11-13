from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.reference import COMPLAINT_REASONS
from app.core.utils import normalize_phone, utcnow
from app.models.billing import Plan
from app.models.enums import (
    ComplaintStatus,
    ListingStatus,
    ListingType,
    MemberStatus,
    PromotionType,
)
from app.models.listing import (
    Complaint,
    Favorite,
    Listing,
    ListingPromotion,
    ListingView,
)
from app.models.organization import OrgMember
from app.models.user import User
from app.schemas.listing import (
    ComplaintCreate,
    ListingCreate,
    ListingUpdate,
)
from app.services import catalog_service, org_service


async def get_listing(db: AsyncSession, listing_id: uuid.UUID) -> Listing:
    listing = await db.scalar(select(Listing).where(Listing.id == listing_id))
    if listing is None or listing.deleted_at is not None:
        raise AppError("Объявление не найдено", status_code=404, code="listing_not_found")
    return listing


async def require_listing_permission(
    db: AsyncSession, user: User, listing: Listing, permission: str
) -> None:
    if listing.user_id == user.id:
        return
    if listing.organization_id:
        await org_service.require_org_permission(
            db, user, listing.organization_id, permission
        )
        return
    raise AppError("Недостаточно прав", status_code=403, code="permission_denied")


async def can_view_listing(db: AsyncSession, user: User | None, listing: Listing) -> bool:
    if listing.deleted_at is not None:
        return False
    status = listing.status.value if hasattr(listing.status, "value") else str(listing.status)
    if status == ListingStatus.ACTIVE.value:
        expires_at = listing.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < utcnow():
                return False
        return True
    if user is None:
        return False
    if listing.user_id == user.id:
        return True
    if listing.organization_id:
        member = await org_service.get_membership(db, user.id, listing.organization_id)
        return member is not None
    return False


async def create_listing(db: AsyncSession, user: User, data: ListingCreate) -> Listing:
    category = await catalog_service.get_category(db, data.category_id)
    if not category.is_active:
        raise AppError(
            "Категория недоступна для публикации",
            status_code=422,
            code="category_inactive",
        )
    category_types = catalog_service.allowed_types(category)
    if data.type.value not in category_types:
        raise AppError(
            "Этот тип объявления не разрешён для категории",
            status_code=422,
            code="listing_type_not_allowed",
            details={"allowed": category_types},
        )
    attributes = await catalog_service.validate_listing_attributes(
        db, category_id=category.id, attributes=data.attributes
    )

    organization = None
    if data.organization_id:
        organization, _, _ = await org_service.require_org_permission(
            db, user, data.organization_id, "listing.create"
        )

    contact_phone = normalize_phone(data.contact_phone)
    if contact_phone is None:
        contact_phone = organization.phone if organization else user.phone
    listing = Listing(
        title=data.title.strip(),
        description=data.description.strip(),
        category_id=category.id,
        type=data.type,
        region=data.region,
        city=data.city,
        address=data.address,
        price=Decimal(str(data.price)) if data.price is not None else None,
        currency=data.currency,
        price_unit=data.price_unit,
        negotiable=data.negotiable,
        attributes=attributes,
        status=ListingStatus.DRAFT,
        user_id=user.id,
        organization_id=organization.id if organization else None,
        is_private_person=organization is None,
        contact_phone=contact_phone,
        contact_telegram=data.contact_telegram or (organization.telegram if organization else None),
        contact_max=data.contact_max or (organization.max_contact if organization else None),
    )
    db.add(listing)
    await db.commit()
    await db.refresh(listing)
    return await get_listing(db, listing.id)


async def update_listing(
    db: AsyncSession, user: User, listing_id: uuid.UUID, data: ListingUpdate
) -> Listing:
    listing = await get_listing(db, listing_id)
    await require_listing_permission(db, user, listing, "listing.edit")
    status = listing.status.value if hasattr(listing.status, "value") else str(listing.status)
    if status in (ListingStatus.BLOCKED.value, ListingStatus.ARCHIVED.value):
        raise AppError(
            "Объявление нельзя редактировать в этом статусе",
            status_code=409,
            code="listing_not_editable",
        )
    values = data.model_dump(exclude_unset=True)

    new_category_id = values.get("category_id", listing.category_id)
    category = await catalog_service.get_category(db, new_category_id)
    if not category.is_active:
        raise AppError("Категория недоступна", status_code=422, code="category_inactive")
    new_type = values.get("type", listing.type)
    if isinstance(new_type, str):
        new_type = ListingType(new_type)
    if new_type.value not in catalog_service.allowed_types(category):
        raise AppError(
            "Этот тип объявления не разрешён для категории",
            status_code=422,
            code="listing_type_not_allowed",
        )

    if "attributes" in values or "category_id" in values:
        attributes = await catalog_service.validate_listing_attributes(
            db,
            category_id=category.id,
            attributes=values.get("attributes", listing.attributes),
        )
        listing.attributes = attributes
    listing.category_id = category.id
    listing.type = new_type

    for field in (
        "title",
        "description",
        "region",
        "city",
        "address",
        "currency",
        "price_unit",
        "negotiable",
        "contact_telegram",
        "contact_max",
    ):
        if field in values:
            value = values[field]
            if field in ("title", "description") and isinstance(value, str):
                value = value.strip()
            setattr(listing, field, value)
    if "price" in values:
        listing.price = Decimal(str(values["price"])) if values["price"] is not None else None
    if "contact_phone" in values:
        listing.contact_phone = normalize_phone(values["contact_phone"])
    if status == ListingStatus.ACTIVE.value:
        listing.status = ListingStatus.PENDING
        listing.submitted_at = utcnow()
        listing.rejection_reason = None
    elif status == ListingStatus.REJECTED.value:
        listing.status = ListingStatus.DRAFT
        listing.rejection_reason = None
    await db.commit()
    await db.refresh(listing)
    return await get_listing(db, listing.id)


async def _active_limit(db: AsyncSession, user: User, organization_id: uuid.UUID | None) -> int:
    if organization_id:
        org = await org_service.get_org(db, organization_id)
        if org.plan and org.plan.is_active:
            return org.plan.max_active_listings
        free_plan = await db.scalar(
            select(Plan).where(Plan.code == "free", Plan.is_active.is_(True))
        )
        return free_plan.max_active_listings if free_plan else 10
    return settings.private_active_listing_limit


async def _check_listing_limit(
    db: AsyncSession, user: User, organization_id: uuid.UUID | None, *, exclude_id: uuid.UUID | None = None
) -> None:
    limit = await _active_limit(db, user, organization_id)
    query = select(func.count(Listing.id)).where(
        Listing.status.in_([ListingStatus.ACTIVE, ListingStatus.PENDING]),
        Listing.deleted_at.is_(None),
    )
    if organization_id:
        query = query.where(Listing.organization_id == organization_id)
    else:
        query = query.where(
            Listing.user_id == user.id,
            Listing.organization_id.is_(None),
        )
    if exclude_id:
        query = query.where(Listing.id != exclude_id)
    count = await db.scalar(query) or 0
    if count >= limit:
        raise AppError(
            "Достигнут лимит активных объявлений",
            status_code=403,
            code="listing_limit_reached",
            details={"limit": limit, "active": int(count)},
        )


async def submit_listing(db: AsyncSession, user: User, listing_id: uuid.UUID) -> Listing:
    listing = await get_listing(db, listing_id)
    await require_listing_permission(db, user, listing, "listing.publish")
    status = listing.status.value if hasattr(listing.status, "value") else str(listing.status)
    if status not in (
        ListingStatus.DRAFT.value,
        ListingStatus.REJECTED.value,
    ):
        raise AppError(
            "Отправить на модерацию можно только черновик или отклонённое объявление",
            status_code=409,
            code="invalid_listing_status",
            details={"status": status},
        )
    await catalog_service.validate_listing_attributes(
        db, category_id=listing.category_id, attributes=listing.attributes
    )
    await _check_listing_limit(
        db,
        user,
        listing.organization_id,
        exclude_id=listing.id,
    )
    listing.status = ListingStatus.PENDING
    listing.submitted_at = utcnow()
    listing.rejection_reason = None
    await db.commit()
    await db.refresh(listing)
    return await get_listing(db, listing.id)


async def archive_listing(db: AsyncSession, user: User, listing_id: uuid.UUID) -> Listing:
    listing = await get_listing(db, listing_id)
    await require_listing_permission(db, user, listing, "listing.edit")
    listing.status = ListingStatus.ARCHIVED
    await db.commit()
    return await get_listing(db, listing.id)


async def delete_listing(db: AsyncSession, user: User, listing_id: uuid.UUID) -> None:
    listing = await get_listing(db, listing_id)
    await require_listing_permission(db, user, listing, "listing.delete")
    listing.deleted_at = utcnow()
    listing.status = ListingStatus.ARCHIVED
    await db.commit()


async def moderate_listing(
    db: AsyncSession,
    admin: User,
    listing_id: uuid.UUID,
    *,
    decision: str,
    reason: str | None = None,
) -> Listing:
    listing = await get_listing(db, listing_id)
    if decision == "approve":
        listing.status = ListingStatus.ACTIVE
        listing.rejection_reason = None
        listing.moderation_comment = None
        if listing.published_at is None:
            listing.published_at = utcnow()
        if listing.bumped_at is None:
            listing.bumped_at = listing.published_at
        listing.expires_at = utcnow() + timedelta(days=settings.default_listing_ttl_days)
    elif decision == "reject":
        if not reason:
            raise AppError(
                "Укажите причину отклонения",
                status_code=422,
                code="rejection_reason_required",
            )
        listing.status = ListingStatus.REJECTED
        listing.rejection_reason = reason
        listing.moderation_comment = reason
    elif decision == "block":
        if not reason:
            raise AppError(
                "Укажите причину блокировки",
                status_code=422,
                code="block_reason_required",
            )
        listing.status = ListingStatus.BLOCKED
        listing.moderation_comment = reason
    else:
        raise AppError("Неизвестное решение", status_code=422, code="invalid_decision")
    listing.moderated_by = admin.id
    listing.moderated_at = utcnow()
    await db.commit()
    await db.refresh(listing)
    return await get_listing(db, listing.id)


async def promote_listing(
    db: AsyncSession,
    admin: User,
    listing_id: uuid.UUID,
    *,
    promotion_type: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
) -> ListingPromotion:
    listing = await get_listing(db, listing_id)
    if listing.status != ListingStatus.ACTIVE:
        raise AppError(
            "Продвигать можно только активное объявление",
            status_code=409,
            code="listing_not_active",
        )
    try:
        promo_type = PromotionType(promotion_type)
    except ValueError as exc:
        raise AppError("Неизвестный тип продвижения", status_code=422, code="invalid_promotion") from exc
    start = starts_at or utcnow()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = ends_at
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end is None:
        end = start + timedelta(days=7)
    promotion = ListingPromotion(
        listing_id=listing.id,
        type=promo_type,
        starts_at=start,
        ends_at=end,
        created_by=admin.id,
    )
    db.add(promotion)
    if promo_type == PromotionType.BUMP:
        listing.bumped_at = start
    await db.commit()
    await db.refresh(promotion)
    return promotion


async def remove_promotion(
    db: AsyncSession, listing_id: uuid.UUID, promotion_id: uuid.UUID
) -> None:
    promotion = await db.scalar(
        select(ListingPromotion).where(
            ListingPromotion.id == promotion_id,
            ListingPromotion.listing_id == listing_id,
        )
    )
    if promotion is None:
        raise AppError("Продвижение не найдено", status_code=404, code="promotion_not_found")
    await db.delete(promotion)
    await db.commit()


async def record_view(
    db: AsyncSession,
    listing_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None,
    ip: str | None,
) -> None:
    ip_hash = hashlib.sha256((ip or "").encode("utf-8")).hexdigest() if ip else None
    listing = await db.get(Listing, listing_id)
    if listing is not None:
        listing.views_count = (listing.views_count or 0) + 1
    db.add(ListingView(listing_id=listing_id, user_id=user_id, ip_hash=ip_hash))
    await db.commit()
    if listing is not None:
        # ``updated_at`` uses a server-side ON UPDATE expression and is expired
        # after the flush; reload just this column for the response.
        await db.refresh(listing, attribute_names=["updated_at"])


async def is_favorite(db: AsyncSession, user_id: uuid.UUID, listing_id: uuid.UUID) -> bool:
    return (
        await db.scalar(
            select(Favorite.id).where(
                Favorite.user_id == user_id,
                Favorite.listing_id == listing_id,
            )
        )
        is not None
    )


async def add_favorite(db: AsyncSession, user: User, listing_id: uuid.UUID) -> None:
    listing = await get_listing(db, listing_id)
    if not await can_view_listing(db, user, listing):
        raise AppError("Объявление недоступно", status_code=404, code="listing_not_found")
    existing = await db.scalar(
        select(Favorite.id).where(
            Favorite.user_id == user.id,
            Favorite.listing_id == listing_id,
        )
    )
    if existing:
        return
    db.add(Favorite(user_id=user.id, listing_id=listing_id))
    listing.favorites_count += 1
    await db.commit()


async def remove_favorite(db: AsyncSession, user: User, listing_id: uuid.UUID) -> None:
    favorite = await db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.listing_id == listing_id,
        )
    )
    if favorite is None:
        return
    listing = await get_listing(db, listing_id)
    listing.favorites_count = max(0, listing.favorites_count - 1)
    await db.delete(favorite)
    await db.commit()


async def list_favorites(
    db: AsyncSession, user: User, *, page: int, per_page: int
) -> tuple[list[Listing], int]:
    query = (
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .where(
            Favorite.user_id == user.id,
            Listing.deleted_at.is_(None),
        )
        .order_by(Favorite.created_at.desc())
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(query.offset((page - 1) * per_page).limit(per_page))
    return list(result.scalars().unique().all()), int(total)


async def list_my_listings(
    db: AsyncSession,
    user: User,
    *,
    status: str | None,
    page: int,
    per_page: int,
) -> tuple[list[Listing], int]:
    org_ids = select(OrgMember.organization_id).where(
        OrgMember.user_id == user.id,
        OrgMember.status == MemberStatus.ACTIVE,
    )
    query = select(Listing).where(
        Listing.deleted_at.is_(None),
        or_(Listing.user_id == user.id, Listing.organization_id.in_(org_ids)),
    )
    if status:
        query = query.where(Listing.status == status)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(Listing.updated_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    return list(result.scalars().unique().all()), int(total)


async def get_listing_stats(db: AsyncSession, user: User, listing_id: uuid.UUID):
    listing = await get_listing(db, listing_id)
    await require_listing_permission(db, user, listing, "listing.view_stats")
    now = utcnow()
    views_7d = await db.scalar(
        select(func.count(ListingView.id)).where(
            ListingView.listing_id == listing.id,
            ListingView.created_at >= now - timedelta(days=7),
        )
    )
    views_30d = await db.scalar(
        select(func.count(ListingView.id)).where(
            ListingView.listing_id == listing.id,
            ListingView.created_at >= now - timedelta(days=30),
        )
    )
    return {
        "listing_id": listing.id,
        "total_views": listing.views_count,
        "views_7d": int(views_7d or 0),
        "views_30d": int(views_30d or 0),
        "favorites_count": listing.favorites_count,
        "status": listing.status.value
        if hasattr(listing.status, "value")
        else str(listing.status),
        "published_at": listing.published_at,
        "expires_at": listing.expires_at,
    }


async def create_complaint(
    db: AsyncSession, user: User, listing_id: uuid.UUID, data: ComplaintCreate
) -> Complaint:
    listing = await get_listing(db, listing_id)
    if data.reason not in COMPLAINT_REASONS:
        raise AppError(
            "Недопустимая причина жалобы",
            status_code=422,
            code="invalid_complaint_reason",
            details={"allowed": sorted(COMPLAINT_REASONS)},
        )
    if listing.user_id == user.id:
        raise AppError(
            "Нельзя пожаловаться на собственное объявление",
            status_code=409,
            code="own_listing_complaint",
        )
    if listing.organization_id:
        member = await org_service.get_membership(db, user.id, listing.organization_id)
        if member is not None:
            raise AppError(
                "Нельзя пожаловаться на объявление своей организации",
                status_code=409,
                code="own_org_complaint",
            )
    complaint = Complaint(
        listing_id=listing.id,
        organization_id=listing.organization_id,
        complainant_id=user.id,
        reason=data.reason,
        comment=data.comment,
        status=ComplaintStatus.NEW,
    )
    db.add(complaint)
    await db.commit()
    return await db.scalar(select(Complaint).where(Complaint.id == complaint.id))


async def expire_listings(db: AsyncSession) -> int:
    result = await db.execute(
        update(Listing)
        .where(
            Listing.status == ListingStatus.ACTIVE,
            Listing.expires_at.is_not(None),
            Listing.expires_at < utcnow(),
            Listing.deleted_at.is_(None),
        )
        .values(status=ListingStatus.EXPIRED)
    )
    await db.commit()
    return int(result.rowcount or 0)
