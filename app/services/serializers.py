from __future__ import annotations

from datetime import datetime, timezone

from app.core.reference import VERIFICATION_LEVELS
from app.models.catalog import Category, CategoryAttribute
from app.models.enums import PromotionType
from app.models.listing import Complaint, Listing, ListingPromotion
from app.models.organization import (
    Organization,
    OrganizationCapability,
    OrgMember,
    OrgRole,
    VerificationDocument,
)
from app.models.system import AuditLog
from app.models.user import User
from app.schemas.catalog import (
    AttributeOut,
    CategoryDetail,
    CategoryOut,
    CategoryShort,
)
from app.schemas.listing import (
    ComplaintOut,
    ListingContacts,
    ListingOut,
    PromotionOut,
)
from app.schemas.organization import (
    DocumentOut,
    MemberOut,
    OrgBrief,
    OrgCapabilityOut,
    OrgOut,
    OrgPublic,
    PlanOut,
    RoleOut,
)
from app.schemas.user import UserMe, UserPublic


def user_me(user: User) -> UserMe:
    return UserMe(
        id=user.id,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        phone=user.phone,
        phone_verified=user.phone_verified_at is not None,
        email=user.email,
        email_verified=user.email_verified_at is not None,
        status=user.status.value if hasattr(user.status, "value") else str(user.status),
        notification_settings=user.notification_settings or {},
        platform_roles=[role.code for role in user.platform_roles],
        created_at=user.created_at,
    )


def user_public(user: User, *, is_private_person: bool = False) -> UserPublic:
    return UserPublic(
        id=user.id,
        full_name=user.full_name,
        telegram_username=user.telegram_username,
        is_private_person=is_private_person,
    )


def plan_out(plan) -> PlanOut | None:
    if plan is None:
        return None
    return PlanOut(
        id=plan.id,
        code=plan.code,
        name=plan.name,
        max_active_listings=plan.max_active_listings,
        price=float(plan.price),
        currency=plan.currency,
        features=plan.features or {},
        description=plan.description,
        is_active=plan.is_active,
        sort_order=plan.sort_order,
    )


def org_capability_out(capability: OrganizationCapability) -> OrgCapabilityOut:
    return OrgCapabilityOut(
        code=capability.code,
        name=capability.capability.name if capability.capability else None,
        params=capability.params or {},
    )


def org_brief(org: Organization) -> OrgBrief:
    return OrgBrief(
        id=org.id,
        slug=org.slug,
        name=org.name,
        type=org.type.value if hasattr(org.type, "value") else str(org.type),
        region=org.region.value if hasattr(org.region, "value") else str(org.region),
        logo_url=org.logo_url,
        verification_level=(
            org.verification_level.value
            if hasattr(org.verification_level, "value")
            else str(org.verification_level)
        ),
    )


def org_out(
    org: Organization,
    *,
    members_count: int = 0,
    active_listings_count: int = 0,
) -> OrgOut:
    level = (
        org.verification_level.value
        if hasattr(org.verification_level, "value")
        else str(org.verification_level)
    )
    return OrgOut(
        id=org.id,
        slug=org.slug,
        type=org.type.value if hasattr(org.type, "value") else str(org.type),
        name=org.name,
        inn=org.inn,
        ogrn=org.ogrn,
        description=org.description,
        logo_url=org.logo_url,
        region=org.region.value if hasattr(org.region, "value") else str(org.region),
        address=org.address,
        website=org.website,
        phone=org.phone,
        telegram=org.telegram,
        max_contact=org.max_contact,
        status=org.status.value if hasattr(org.status, "value") else str(org.status),
        verification_level=level,
        verification_label=VERIFICATION_LEVELS.get(level),
        phone_verified=org.phone_verified_at is not None,
        inn_verified=org.inn_verified_at is not None,
        moderator_verified=org.moderator_verified_at is not None,
        rejection_reason=org.rejection_reason,
        plan=plan_out(org.plan),
        capabilities=[org_capability_out(cap) for cap in org.capabilities],
        members_count=members_count,
        active_listings_count=active_listings_count,
        created_at=org.created_at,
    )


def org_public(
    org: Organization,
    *,
    active_listings_count: int = 0,
    owner_name: str | None = None,
) -> OrgPublic:
    level = (
        org.verification_level.value
        if hasattr(org.verification_level, "value")
        else str(org.verification_level)
    )
    return OrgPublic(
        id=org.id,
        slug=org.slug,
        type=org.type.value if hasattr(org.type, "value") else str(org.type),
        name=org.name,
        description=org.description,
        logo_url=org.logo_url,
        region=org.region.value if hasattr(org.region, "value") else str(org.region),
        address=org.address,
        website=org.website,
        phone=org.phone,
        telegram=org.telegram,
        max_contact=org.max_contact,
        verification_level=level,
        verification_label=VERIFICATION_LEVELS.get(level),
        capabilities=[org_capability_out(cap) for cap in org.capabilities],
        active_listings_count=active_listings_count,
        owner_name=owner_name,
        created_at=org.created_at,
    )


def role_out(role: OrgRole, *, members_count: int = 0) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        permissions=role.permissions or [],
        is_system=role.is_system,
        members_count=members_count,
    )


def member_out(member: OrgMember) -> MemberOut:
    return MemberOut(
        id=member.id,
        user_id=member.user_id,
        full_name=member.user.full_name,
        telegram_username=member.user.telegram_username,
        phone=member.user.phone,
        role=role_out(member.role) if member.role else None,
        is_owner=member.is_owner,
        status=member.status.value if hasattr(member.status, "value") else str(member.status),
        joined_at=member.joined_at,
    )


def category_short(category: Category) -> CategoryShort:
    return CategoryShort(
        id=category.id,
        slug=category.slug,
        name=category.name,
        parent_id=category.parent_id,
    )


def attribute_out(attribute: CategoryAttribute) -> AttributeOut:
    return AttributeOut(
        id=attribute.id,
        key=attribute.key,
        name=attribute.name,
        type=attribute.type.value if hasattr(attribute.type, "value") else str(attribute.type),
        unit=attribute.unit,
        is_required=attribute.is_required,
        is_filterable=attribute.is_filterable,
        options=attribute.options or [],
        sort_order=attribute.sort_order,
    )


def category_out(category: Category, *, include_children: bool = False) -> CategoryOut:
    return CategoryOut(
        id=category.id,
        parent_id=category.parent_id,
        slug=category.slug,
        name=category.name,
        description=category.description,
        sort_order=category.sort_order,
        is_active=category.is_active,
        allowed_types=list(category.allowed_types or []),
        attributes=[attribute_out(attr) for attr in category.attributes],
        children=(
            [category_out(child, include_children=True) for child in category.children]
            if include_children
            else []
        ),
    )


def category_detail(
    category: Category,
    *,
    ancestors: list[Category],
    inherited_attributes: list[CategoryAttribute],
) -> CategoryDetail:
    base = category_out(category)
    return CategoryDetail(
        **base.model_dump(),
        ancestors=[category_short(item) for item in ancestors],
        inherited_attributes=[attribute_out(attr) for attr in inherited_attributes],
    )


def document_out(document: VerificationDocument) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        kind=document.kind.value if hasattr(document.kind, "value") else str(document.kind),
        file_url=document.file_url,
        original_name=document.original_name,
        status=document.status.value
        if hasattr(document.status, "value")
        else str(document.status),
        review_comment=document.review_comment,
        created_at=document.created_at,
        reviewed_at=document.reviewed_at,
    )


def active_promotions(listing: Listing, now: datetime | None = None) -> list[ListingPromotion]:
    now = now or datetime.now(timezone.utc)
    result: list[ListingPromotion] = []
    for promotion in listing.promotions:
        starts_at = promotion.starts_at
        ends_at = promotion.ends_at
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
        if ends_at is not None and ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=timezone.utc)
        if starts_at <= now and (ends_at is None or ends_at > now):
            result.append(promotion)
    return result


def listing_out(
    listing: Listing,
    *,
    contacts_visible: bool,
    is_favorite: bool = False,
) -> ListingOut:
    org = listing.organization
    promotions = active_promotions(listing)
    promotion_types = {
        promo.type.value if hasattr(promo.type, "value") else str(promo.type)
        for promo in promotions
    }
    phone = listing.contact_phone or (org.phone if org else None) or (listing.user.phone if listing.user else None)
    telegram = listing.contact_telegram or (org.telegram if org else None)
    max_contact = listing.contact_max or (org.max_contact if org else None)
    return ListingOut(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        category=category_short(listing.category) if listing.category else None,
        organization=org_brief(org) if org else None,
        user=user_public(listing.user, is_private_person=listing.is_private_person)
        if listing.user
        else None,
        type=listing.type.value if hasattr(listing.type, "value") else str(listing.type),
        region=listing.region.value if hasattr(listing.region, "value") else str(listing.region),
        city=listing.city,
        address=listing.address,
        price=float(listing.price) if listing.price is not None else None,
        currency=listing.currency,
        price_unit=listing.price_unit,
        negotiable=listing.negotiable,
        attributes=listing.attributes or {},
        status=listing.status.value if hasattr(listing.status, "value") else str(listing.status),
        rejection_reason=listing.rejection_reason,
        is_private_person=listing.is_private_person,
        contacts=(
            ListingContacts(phone=phone, telegram=telegram, max_contact=max_contact)
            if contacts_visible
            else None
        ),
        contacts_available=contacts_visible,
        promotions=[
            PromotionOut(
                id=promo.id,
                type=promo.type.value if hasattr(promo.type, "value") else str(promo.type),
                starts_at=promo.starts_at,
                ends_at=promo.ends_at,
            )
            for promo in promotions
        ],
        is_top=PromotionType.TOP.value in promotion_types,
        is_highlight=PromotionType.HIGHLIGHT.value in promotion_types,
        published_at=listing.published_at,
        expires_at=listing.expires_at,
        bumped_at=listing.bumped_at,
        views_count=listing.views_count,
        favorites_count=listing.favorites_count,
        is_favorite=is_favorite,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
    )


def complaint_out(complaint: Complaint) -> ComplaintOut:
    return ComplaintOut(
        id=complaint.id,
        listing_id=complaint.listing_id,
        organization_id=complaint.organization_id,
        target_user_id=complaint.target_user_id,
        reason=complaint.reason,
        comment=complaint.comment,
        status=complaint.status.value
        if hasattr(complaint.status, "value")
        else str(complaint.status),
        resolution=complaint.resolution,
        complainant=user_public(complaint.complainant) if complaint.complainant else None,
        created_at=complaint.created_at,
        handled_at=complaint.handled_at,
    )


def audit_out(entry: AuditLog):
    from app.schemas.admin import AuditOut

    return AuditOut(
        id=entry.id,
        actor_id=entry.actor_id,
        action=entry.action,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        payload=entry.payload or {},
        ip=entry.ip,
        created_at=entry.created_at,
    )


def admin_user_out(user: User, *, organizations_count: int = 0):
    from app.schemas.admin import AdminUserOut

    return AdminUserOut(
        id=user.id,
        telegram_id=user.telegram_id,
        full_name=user.full_name,
        phone=user.phone,
        email=user.email,
        status=user.status.value if hasattr(user.status, "value") else str(user.status),
        platform_roles=[role.code for role in user.platform_roles],
        organizations_count=organizations_count,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        blocked_reason=user.blocked_reason,
    )
