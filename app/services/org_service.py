from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import cache
from app.core.config import settings
from app.core.errors import AppError
from app.core.inn import check_inn
from app.core.permissions import (
    ALL_ORG_PERMISSIONS,
    DEFAULT_ORG_ROLES,
    ORG_PERMISSIONS,
    is_subset,
)
from app.core.reference import ORG_TYPE_INN_LENGTH
from app.core.security import hash_token, new_url_token
from app.core.telegram import telegram_bot
from app.core.utils import clean_str, normalize_inn, normalize_phone, slugify_text
from app.models.billing import Plan
from app.models.enums import (
    DocumentKind,
    DocumentStatus,
    InvitationStatus,
    MemberStatus,
    OrgStatus,
    OrgType,
    VerificationLevel,
)
from app.models.listing import Listing, ListingStatus
from app.models.organization import (
    Capability,
    Invitation,
    Organization,
    OrganizationCapability,
    OrgMember,
    OrgRole,
    VerificationDocument,
)
from app.models.user import User
from app.schemas.organization import (
    CapabilitiesUpdate,
    DocumentOut,
    InvitationCreated,
    InvitationOut,
    MemberOut,
    OrgCreate,
    OrgOut,
    OrgPublic,
    OrgUpdate,
    RoleCreate,
    RoleOut,
    RoleUpdate,
)
from app.services.serializers import (
    document_out,
    member_out,
    org_out,
    org_public,
    role_out,
)

PERMISSION_CACHE_TTL = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _permission_key(org_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"perms:org:{org_id}:user:{user_id}"


async def invalidate_org_permissions(org_id: uuid.UUID) -> None:
    await cache.delete_prefix(f"perms:org:{org_id}:")


async def invalidate_user_org_permissions(org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    await cache.delete(_permission_key(org_id, user_id))


def _level_of(org: Organization) -> str:
    if org.moderator_verified_at:
        return VerificationLevel.MODERATOR.value
    if org.inn_verified_at:
        return VerificationLevel.INN.value
    if org.phone_verified_at:
        return VerificationLevel.PHONE.value
    return VerificationLevel.NONE.value


def _apply_level(org: Organization) -> None:
    org.verification_level = VerificationLevel(_level_of(org))


async def get_org(db: AsyncSession, org_id: uuid.UUID) -> Organization:
    org = await db.scalar(
        select(Organization)
        .where(Organization.id == org_id)
        .options(
            selectinload(Organization.capabilities).selectinload(
                OrganizationCapability.capability
            )
        )
    )
    if org is None:
        raise AppError("Организация не найдена", status_code=404, code="organization_not_found")
    return org


async def get_org_counts(db: AsyncSession, org_id: uuid.UUID) -> tuple[int, int]:
    members = await db.scalar(
        select(func.count(OrgMember.id)).where(
            OrgMember.organization_id == org_id,
            OrgMember.status == MemberStatus.ACTIVE,
        )
    )
    active_listings = await db.scalar(
        select(func.count(Listing.id)).where(
            Listing.organization_id == org_id,
            Listing.status == ListingStatus.ACTIVE,
            Listing.deleted_at.is_(None),
        )
    )
    return int(members or 0), int(active_listings or 0)


async def get_org_out(db: AsyncSession, org: Organization) -> OrgOut:
    members, active = await get_org_counts(db, org.id)
    return org_out(org, members_count=members, active_listings_count=active)


async def _unique_slug(db: AsyncSession, base: str, *, exclude_id: uuid.UUID | None = None) -> str:
    base_slug = slugify_text(base, fallback="org")
    candidate = base_slug
    suffix = 2
    while True:
        query = select(Organization.id).where(Organization.slug == candidate)
        if exclude_id:
            query = query.where(Organization.id != exclude_id)
        if not await db.scalar(query):
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _validate_inn_for_type(org_type: OrgType, inn: str | None) -> tuple[str | None, bool]:
    if not inn:
        return None, False
    expected = ORG_TYPE_INN_LENGTH.get(
        org_type.value if hasattr(org_type, "value") else str(org_type)
    )
    result = check_inn(inn, expected_length=expected)
    if not result.valid:
        raise AppError(
            result.reason or "ИНН не прошёл проверку",
            status_code=422,
            code="invalid_inn",
        )
    return result.inn, True


async def _validate_capabilities(
    db: AsyncSession, items: list
) -> list[OrganizationCapability]:
    if not items:
        return []
    codes = [item.code for item in items]
    if len(codes) != len(set(codes)):
        raise AppError(
            "Возможности не должны повторяться",
            status_code=422,
            code="duplicate_capability",
        )
    result = await db.execute(
        select(Capability).where(Capability.code.in_(codes), Capability.is_active.is_(True))
    )
    known = {item.code for item in result.scalars().all()}
    unknown = [code for code in codes if code not in known]
    if unknown:
        raise AppError(
            "Неизвестные возможности организации",
            status_code=422,
            code="unknown_capability",
            details={"unknown": unknown, "allowed": sorted(known)},
        )
    return [
        OrganizationCapability(code=item.code, params=item.params or {}) for item in items
    ]


async def create_organization(db: AsyncSession, user: User, data: OrgCreate) -> Organization:
    inn, inn_ok = _validate_inn_for_type(data.type, data.inn)
    phone = normalize_phone(data.phone)
    slug = await _unique_slug(db, data.slug or data.name)
    org = Organization(
        slug=slug,
        type=data.type,
        name=data.name.strip(),
        inn=inn,
        ogrn=clean_str(data.ogrn),
        description=clean_str(data.description),
        logo_url=clean_str(data.logo_url),
        region=data.region,
        address=clean_str(data.address),
        website=clean_str(data.website),
        phone=phone,
        telegram=clean_str(data.telegram),
        max_contact=clean_str(data.max_contact),
        created_by=user.id,
        status=OrgStatus.ACTIVE,
    )
    if inn_ok:
        org.inn_verified_at = _now()
    if phone and user.phone_verified_at:
        org.phone_verified_at = _now()
    _apply_level(org)

    free_plan = await db.scalar(select(Plan).where(Plan.code == "free", Plan.is_active.is_(True)))
    if free_plan:
        org.plan_id = free_plan.id

    db.add(org)
    await db.flush()

    member = OrgMember(
        organization_id=org.id,
        user_id=user.id,
        is_owner=True,
        status=MemberStatus.ACTIVE,
        joined_at=_now(),
    )
    db.add(member)
    for template in DEFAULT_ORG_ROLES:
        db.add(
            OrgRole(
                organization_id=org.id,
                name=template["name"],
                permissions=list(template["permissions"]),
                is_system=True,
                created_by=user.id,
            )
        )
    caps = await _validate_capabilities(db, data.capabilities)
    for cap in caps:
        cap.organization_id = org.id
        db.add(cap)
    await db.commit()
    await db.refresh(org)
    await invalidate_org_permissions(org.id)
    return await get_org(db, org.id)


async def update_organization(
    db: AsyncSession, user: User, org_id: uuid.UUID, data: OrgUpdate
) -> Organization:
    org, member, permissions = await require_org_permission(db, user, org_id, None)
    values = data.model_dump(exclude_unset=True)
    contact_fields = {"phone", "telegram", "max_contact"}
    profile_fields = set(values) - contact_fields
    if not member.is_owner:
        if profile_fields and "org.edit_profile" not in permissions:
            raise AppError(
                "Нет разрешения на редактирование профиля",
                status_code=403,
                code="permission_denied",
                details={"required": "org.edit_profile"},
            )
        if contact_fields & set(values) and "org.manage_contacts" not in permissions:
            raise AppError(
                "Нет разрешения на управление контактами",
                status_code=403,
                code="permission_denied",
                details={"required": "org.manage_contacts"},
            )

    if "name" in values and values["name"] is not None:
        org.name = values["name"].strip()
    if "type" in values and values["type"] is not None:
        org.type = OrgType(values["type"])
    if "inn" in values:
        if values["inn"]:
            inn, ok = _validate_inn_for_type(org.type, values["inn"])
            org.inn = inn
            if ok:
                org.inn_verified_at = _now()
        else:
            org.inn = None
            org.inn_verified_at = None
    if "ogrn" in values:
        org.ogrn = clean_str(values["ogrn"])
    if "description" in values:
        org.description = clean_str(values["description"])
    if "logo_url" in values:
        org.logo_url = clean_str(values["logo_url"])
    if "region" in values and values["region"] is not None:
        org.region = values["region"]
    if "address" in values:
        org.address = clean_str(values["address"])
    if "website" in values:
        org.website = clean_str(values["website"])
    if "phone" in values:
        org.phone = normalize_phone(values["phone"])
    if "telegram" in values:
        org.telegram = clean_str(values["telegram"])
    if "max_contact" in values:
        org.max_contact = clean_str(values["max_contact"])
    if "slug" in values and values["slug"]:
        slug = slugify_text(values["slug"], fallback="org")
        if slug != org.slug:
            org.slug = await _unique_slug(db, slug, exclude_id=org.id)
    _apply_level(org)
    await db.commit()
    await db.refresh(org)
    return await get_org(db, org.id)


async def set_capabilities(
    db: AsyncSession, user: User, org_id: uuid.UUID, data: CapabilitiesUpdate
) -> Organization:
    org, member, permissions = await require_org_permission(db, user, org_id, None)
    if not member.is_owner and "org.edit_profile" not in permissions:
        raise AppError(
            "Нет разрешения на редактирование профиля",
            status_code=403,
            code="permission_denied",
            details={"required": "org.edit_profile"},
        )
    caps = await _validate_capabilities(db, data.capabilities)
    org.capabilities.clear()
    await db.flush()
    for cap in caps:
        cap.organization_id = org.id
        db.add(cap)
    await db.commit()
    await db.refresh(org)
    return await get_org(db, org.id)


async def list_my_organizations(db: AsyncSession, user: User) -> list[OrgOut]:
    result = await db.execute(
        select(Organization)
        .join(OrgMember, OrgMember.organization_id == Organization.id)
        .where(
            OrgMember.user_id == user.id,
            OrgMember.status == MemberStatus.ACTIVE,
        )
        .options(
            selectinload(Organization.capabilities).selectinload(
                OrganizationCapability.capability
            )
        )
        .order_by(Organization.created_at.desc())
    )
    orgs = list(result.scalars().unique().all())
    return [await get_org_out(db, org) for org in orgs]


async def get_membership(
    db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID
) -> OrgMember | None:
    return await db.scalar(
        select(OrgMember).where(
            OrgMember.organization_id == org_id,
            OrgMember.user_id == user_id,
            OrgMember.status == MemberStatus.ACTIVE,
        )
    )


async def require_member(
    db: AsyncSession, user: User, org_id: uuid.UUID
) -> tuple[Organization, OrgMember]:
    org = await get_org(db, org_id)
    member = await get_membership(db, user.id, org_id)
    if member is None:
        raise AppError(
            "Вы не являетесь участником организации",
            status_code=403,
            code="not_org_member",
        )
    return org, member


async def require_org_permission(
    db: AsyncSession,
    user: User,
    org_id: uuid.UUID,
    permission: str | None,
) -> tuple[Organization, OrgMember, set[str]]:
    org = await get_org(db, org_id)
    cache_key = _permission_key(org_id, user.id)
    cached = await cache.get_json(cache_key)
    if cached and cached.get("member_id"):
        permissions = set(cached.get("permissions") or [])
        is_owner = bool(cached.get("is_owner"))
        member = await get_membership(db, user.id, org_id)
        if member is None:
            await cache.delete(cache_key)
            raise AppError(
                "Вы не являетесь участником организации",
                status_code=403,
                code="not_org_member",
            )
        if permission and not is_owner and permission not in permissions:
            raise AppError(
                "Недостаточно прав",
                status_code=403,
                code="permission_denied",
                details={"required": permission},
            )
        return org, member, permissions

    member = await get_membership(db, user.id, org_id)
    if member is None:
        raise AppError(
            "Вы не являетесь участником организации",
            status_code=403,
            code="not_org_member",
        )
    permissions = (
        set(ALL_ORG_PERMISSIONS)
        if member.is_owner
        else set(member.role.permissions if member.role else [])
    )
    await cache.set_json(
        cache_key,
        {
            "member_id": str(member.id),
            "is_owner": member.is_owner,
            "permissions": sorted(permissions),
        },
        ttl=PERMISSION_CACHE_TTL,
    )
    if permission and not member.is_owner and permission not in permissions:
        raise AppError(
            "Недостаточно прав",
            status_code=403,
            code="permission_denied",
            details={"required": permission},
        )
    return org, member, permissions


async def verify_inn(
    db: AsyncSession, user: User, org_id: uuid.UUID, inn_value: str
) -> Organization:
    org, member, permissions = await require_org_permission(db, user, org_id, None)
    if not member.is_owner and "org.edit_profile" not in permissions:
        raise AppError("Недостаточно прав", status_code=403, code="permission_denied")
    inn = normalize_inn(inn_value)
    expected = ORG_TYPE_INN_LENGTH.get(
        org.type.value if hasattr(org.type, "value") else str(org.type)
    )
    result = check_inn(inn or "", expected_length=expected)
    if not result.valid:
        raise AppError(
            result.reason or "ИНН не прошёл проверку",
            status_code=422,
            code="invalid_inn",
        )
    duplicate = await db.scalar(
        select(Organization.id).where(
            Organization.inn == result.inn,
            Organization.id != org.id,
        )
    )
    if duplicate:
        raise AppError("Организация с таким ИНН уже существует", status_code=409, code="inn_taken")
    org.inn = result.inn
    org.inn_verified_at = _now()
    _apply_level(org)
    await db.commit()
    await db.refresh(org)
    return await get_org(db, org.id)


async def add_verification_document(
    db: AsyncSession,
    user: User,
    org_id: uuid.UUID,
    *,
    kind: DocumentKind,
    file_url: str,
    original_name: str | None,
) -> DocumentOut:
    org, member, permissions = await require_org_permission(db, user, org_id, None)
    if not member.is_owner and "org.edit_profile" not in permissions:
        raise AppError("Недостаточно прав", status_code=403, code="permission_denied")
    document = VerificationDocument(
        organization_id=org.id,
        kind=kind,
        file_url=file_url,
        original_name=original_name,
        status=DocumentStatus.PENDING,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    return document_out(document)


async def list_verification_documents(
    db: AsyncSession, user: User, org_id: uuid.UUID
) -> list[DocumentOut]:
    await require_member(db, user, org_id)
    result = await db.execute(
        select(VerificationDocument)
        .where(VerificationDocument.organization_id == org_id)
        .order_by(VerificationDocument.created_at.desc())
    )
    return [document_out(item) for item in result.scalars().all()]


async def review_verification_document(
    db: AsyncSession,
    admin: User,
    document_id: uuid.UUID,
    *,
    decision: str,
    comment: str | None,
) -> DocumentOut:
    document = await db.get(VerificationDocument, document_id)
    if document is None:
        raise AppError("Документ не найден", status_code=404, code="document_not_found")
    org = await get_org(db, document.organization_id)
    if decision == "approve":
        document.status = DocumentStatus.APPROVED
        document.reviewed_by = admin.id
        document.reviewed_at = _now()
        document.review_comment = comment
        org.moderator_verified_at = _now()
        org.verified_by = admin.id
        org.rejection_reason = None
        _apply_level(org)
    else:
        if not comment:
            raise AppError(
                "Укажите причину отклонения",
                status_code=422,
                code="rejection_reason_required",
            )
        document.status = DocumentStatus.REJECTED
        document.reviewed_by = admin.id
        document.reviewed_at = _now()
        document.review_comment = comment
        org.rejection_reason = comment
    await db.commit()
    await db.refresh(document)
    return document_out(document)


async def list_members(db: AsyncSession, user: User, org_id: uuid.UUID) -> list[MemberOut]:
    await require_member(db, user, org_id)
    result = await db.execute(
        select(OrgMember)
        .where(
            OrgMember.organization_id == org_id,
            OrgMember.status == MemberStatus.ACTIVE,
        )
        .order_by(OrgMember.is_owner.desc(), OrgMember.joined_at)
    )
    return [member_out(item) for item in result.scalars().unique().all()]


async def list_roles(db: AsyncSession, user: User, org_id: uuid.UUID) -> list[RoleOut]:
    await require_member(db, user, org_id)
    result = await db.execute(
        select(OrgRole).where(OrgRole.organization_id == org_id).order_by(OrgRole.name)
    )
    roles = list(result.scalars().all())
    counts = await db.execute(
        select(OrgMember.role_id, func.count(OrgMember.id))
        .where(
            OrgMember.organization_id == org_id,
            OrgMember.status == MemberStatus.ACTIVE,
            OrgMember.role_id.is_not(None),
        )
        .group_by(OrgMember.role_id)
    )
    count_map = {role_id: count for role_id, count in counts.all()}
    return [role_out(role, members_count=count_map.get(role.id, 0)) for role in roles]


def _validate_permission_codes(permissions: list[str]) -> list[str]:
    unknown = [item for item in permissions if item not in ORG_PERMISSIONS]
    if unknown:
        raise AppError(
            "Неизвестные разрешения",
            status_code=422,
            code="unknown_permission",
            details={"unknown": unknown, "allowed": sorted(ORG_PERMISSIONS)},
        )
    return list(dict.fromkeys(permissions))


async def create_role(
    db: AsyncSession, user: User, org_id: uuid.UUID, data: RoleCreate
) -> RoleOut:
    org, member, permissions = await require_org_permission(db, user, org_id, "org.manage_roles")
    requested = _validate_permission_codes(data.permissions)
    if not member.is_owner and not is_subset(requested, permissions):
        raise AppError(
            "Нельзя выдать разрешения, которых нет у вас",
            status_code=403,
            code="permission_escalation",
            details={"missing": sorted(set(requested) - permissions)},
        )
    duplicate = await db.scalar(
        select(OrgRole.id).where(
            OrgRole.organization_id == org_id,
            OrgRole.name == data.name.strip(),
        )
    )
    if duplicate:
        raise AppError("Роль с таким названием уже существует", status_code=409, code="role_exists")
    role = OrgRole(
        organization_id=org_id,
        name=data.name.strip(),
        permissions=requested,
        is_system=False,
        created_by=user.id,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role_out(role)


async def update_role(
    db: AsyncSession, user: User, org_id: uuid.UUID, role_id: uuid.UUID, data: RoleUpdate
) -> RoleOut:
    org, member, permissions = await require_org_permission(db, user, org_id, "org.manage_roles")
    role = await db.scalar(
        select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == org_id)
    )
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    if data.name is not None and data.name.strip() != role.name:
        duplicate = await db.scalar(
            select(OrgRole.id).where(
                OrgRole.organization_id == org_id,
                OrgRole.name == data.name.strip(),
                OrgRole.id != role.id,
            )
        )
        if duplicate:
            raise AppError("Роль с таким названием уже существует", status_code=409, code="role_exists")
        role.name = data.name.strip()
    if data.permissions is not None:
        requested = _validate_permission_codes(data.permissions)
        if not member.is_owner and not is_subset(requested, permissions):
            raise AppError(
                "Нельзя выдать разрешения, которых нет у вас",
                status_code=403,
                code="permission_escalation",
                details={"missing": sorted(set(requested) - permissions)},
            )
        role.permissions = requested
    await db.commit()
    await db.refresh(role)
    await invalidate_org_permissions(org_id)
    return role_out(role)


async def delete_role(
    db: AsyncSession, user: User, org_id: uuid.UUID, role_id: uuid.UUID
) -> None:
    org, member, permissions = await require_org_permission(db, user, org_id, "org.manage_roles")
    role = await db.scalar(
        select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == org_id)
    )
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    assigned = await db.scalar(
        select(func.count(OrgMember.id)).where(
            OrgMember.role_id == role.id,
            OrgMember.status == MemberStatus.ACTIVE,
        )
    )
    if assigned:
        raise AppError(
            "Роль назначена сотрудникам. Сначала переназначьте их.",
            status_code=409,
            code="role_in_use",
            details={"members_count": int(assigned)},
        )
    await db.delete(role)
    await db.commit()
    await invalidate_org_permissions(org_id)


async def invite_member(
    db: AsyncSession,
    user: User,
    org_id: uuid.UUID,
    *,
    role_id: uuid.UUID | None,
    telegram_id: int | None,
) -> InvitationCreated:
    org, member, permissions = await require_org_permission(db, user, org_id, "org.manage_members")
    if role_id is None:
        raise AppError("Укажите роль для приглашения", status_code=422, code="role_required")
    role = await db.scalar(
        select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == org_id)
    )
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    if not member.is_owner and not is_subset(role.permissions or [], permissions):
        raise AppError(
            "Нельзя пригласить сотрудника с разрешениями, которых нет у вас",
            status_code=403,
            code="permission_escalation",
        )
    raw_token = new_url_token(32)
    invitation = Invitation(
        organization_id=org.id,
        role_id=role.id,
        token_hash=hash_token(raw_token),
        created_by=user.id,
        telegram_id=telegram_id,
        status=InvitationStatus.PENDING,
        expires_at=_now() + timedelta(hours=settings.invitation_ttl_hours),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)
    return InvitationCreated(
        id=invitation.id,
        token=raw_token,
        invite_url=telegram_bot.invite_link(raw_token),
        expires_at=invitation.expires_at,
    )


async def list_invitations(
    db: AsyncSession, user: User, org_id: uuid.UUID
) -> list[InvitationOut]:
    await require_org_permission(db, user, org_id, "org.manage_members")
    result = await db.execute(
        select(Invitation)
        .where(Invitation.organization_id == org_id)
        .order_by(Invitation.created_at.desc())
    )
    invitations = list(result.scalars().unique().all())
    return [
        InvitationOut(
            id=item.id,
            role=role_out(item.role) if item.role else None,
            telegram_id=item.telegram_id,
            status=item.status.value
            if hasattr(item.status, "value")
            else str(item.status),
            expires_at=item.expires_at,
            accepted_at=item.accepted_at,
            created_at=item.created_at,
        )
        for item in invitations
    ]


async def revoke_invitation(
    db: AsyncSession, user: User, org_id: uuid.UUID, invitation_id: uuid.UUID
) -> None:
    await require_org_permission(db, user, org_id, "org.manage_members")
    invitation = await db.scalar(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.organization_id == org_id,
        )
    )
    if invitation is None:
        raise AppError("Приглашение не найдено", status_code=404, code="invitation_not_found")
    if invitation.status == InvitationStatus.PENDING:
        invitation.status = InvitationStatus.REVOKED
        await db.commit()


async def _accept_invitation_row(
    db: AsyncSession, invitation: Invitation, user: User
) -> None:
    if invitation.status != InvitationStatus.PENDING:
        raise AppError(
            "Приглашение уже использовано или отозвано",
            status_code=410,
            code="invitation_not_pending",
        )
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        invitation.status = InvitationStatus.EXPIRED
        await db.commit()
        raise AppError("Приглашение истекло", status_code=410, code="invitation_expired")
    if invitation.telegram_id and user.telegram_id and invitation.telegram_id != user.telegram_id:
        raise AppError(
            "Приглашение выдано другому пользователю",
            status_code=403,
            code="invitation_owner_mismatch",
        )
    existing = await db.scalar(
        select(OrgMember).where(
            OrgMember.organization_id == invitation.organization_id,
            OrgMember.user_id == user.id,
        )
    )
    if existing is not None:
        if existing.status == MemberStatus.REMOVED:
            existing.status = MemberStatus.ACTIVE
            existing.role_id = invitation.role_id
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = _now()
        invitation.accepted_by = user.id
        await db.commit()
        await invalidate_user_org_permissions(invitation.organization_id, user.id)
        return
    role = None
    if invitation.role_id:
        role = await db.scalar(
            select(OrgRole).where(
                OrgRole.id == invitation.role_id,
                OrgRole.organization_id == invitation.organization_id,
            )
        )
    member = OrgMember(
        organization_id=invitation.organization_id,
        user_id=user.id,
        role_id=role.id if role else None,
        is_owner=False,
        status=MemberStatus.ACTIVE,
        invited_by=invitation.created_by,
        joined_at=_now(),
    )
    db.add(member)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = _now()
    invitation.accepted_by = user.id
    await db.commit()
    await invalidate_user_org_permissions(invitation.organization_id, user.id)


async def accept_invitation(db: AsyncSession, user: User, raw_token: str) -> OrgOut:
    invitation = await db.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(raw_token))
    )
    if invitation is None:
        raise AppError("Приглашение не найдено", status_code=404, code="invitation_not_found")
    await _accept_invitation_row(db, invitation, user)
    org = await get_org(db, invitation.organization_id)
    return await get_org_out(db, org)


async def accept_pending_invites(db: AsyncSession, user: User) -> None:
    if not user.telegram_id:
        return
    result = await db.execute(
        select(Invitation).where(
            Invitation.telegram_id == user.telegram_id,
            Invitation.status == InvitationStatus.PENDING,
        )
    )
    for invitation in result.scalars().unique().all():
        try:
            await _accept_invitation_row(db, invitation, user)
        except AppError:
            continue


async def update_member_role(
    db: AsyncSession,
    user: User,
    org_id: uuid.UUID,
    member_user_id: uuid.UUID,
    role_id: uuid.UUID | None,
) -> MemberOut:
    org, actor, permissions = await require_org_permission(
        db, user, org_id, "org.manage_members"
    )
    target = await get_membership(db, member_user_id, org_id)
    if target is None:
        raise AppError("Сотрудник не найден", status_code=404, code="member_not_found")
    if target.is_owner:
        raise AppError(
            "Нельзя изменить роль владельца. Передайте владение явно.",
            status_code=409,
            code="owner_role_immutable",
        )
    if role_id is not None:
        role = await db.scalar(
            select(OrgRole).where(OrgRole.id == role_id, OrgRole.organization_id == org_id)
        )
        if role is None:
            raise AppError("Роль не найдена", status_code=404, code="role_not_found")
        if not actor.is_owner and not is_subset(role.permissions or [], permissions):
            raise AppError(
                "Нельзя назначить роль с разрешениями, которых нет у вас",
                status_code=403,
                code="permission_escalation",
            )
        target.role_id = role.id
        target.role = role
    else:
        target.role_id = None
        target.role = None
    await db.commit()
    await invalidate_user_org_permissions(org_id, member_user_id)
    fresh = await get_membership(db, member_user_id, org_id)
    if fresh is None:
        raise AppError("Сотрудник не найден", status_code=404, code="member_not_found")
    return member_out(fresh)


async def remove_member(
    db: AsyncSession, user: User, org_id: uuid.UUID, member_user_id: uuid.UUID
) -> None:
    await require_org_permission(db, user, org_id, "org.manage_members")
    target = await get_membership(db, member_user_id, org_id)
    if target is None:
        raise AppError("Сотрудник не найден", status_code=404, code="member_not_found")
    if target.is_owner:
        raise AppError(
            "Нельзя удалить владельца организации",
            status_code=409,
            code="owner_cannot_be_removed",
        )
    target.status = MemberStatus.REMOVED
    target.role_id = None
    await db.commit()
    await invalidate_user_org_permissions(org_id, member_user_id)


async def transfer_owner(
    db: AsyncSession, user: User, org_id: uuid.UUID, new_owner_id: uuid.UUID
) -> OrgOut:
    org, member = await require_member(db, user, org_id)
    if not member.is_owner:
        raise AppError(
            "Только владелец может передать владение",
            status_code=403,
            code="owner_required",
        )
    target = await get_membership(db, new_owner_id, org_id)
    if target is None:
        raise AppError("Пользователь не является сотрудником", status_code=404, code="member_not_found")
    if target.user_id == member.user_id:
        return await get_org_out(db, org)
    member.is_owner = False
    member.role_id = None
    target.is_owner = True
    target.role_id = None
    await db.commit()
    await invalidate_org_permissions(org_id)
    return await get_org_out(db, org)


async def search_organizations(
    db: AsyncSession,
    *,
    q: str | None,
    region: str | None,
    org_type: str | None,
    capability: str | None,
    verification_level: str | None,
    page: int,
    per_page: int,
) -> tuple[list[OrgPublic], int]:
    query = select(Organization).where(
        Organization.status == OrgStatus.ACTIVE,
        Organization.slug.is_not(None),
    )
    if region:
        query = query.where(Organization.region == region)
    if org_type:
        query = query.where(Organization.type == org_type)
    if verification_level:
        query = query.where(Organization.verification_level == verification_level)
    if capability:
        query = query.where(
            Organization.id.in_(
                select(OrganizationCapability.organization_id).where(
                    OrganizationCapability.code == capability
                )
            )
        )
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Organization.name.ilike(pattern),
                Organization.description.ilike(pattern),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = (
        query.options(
            selectinload(Organization.capabilities).selectinload(
                OrganizationCapability.capability
            )
        )
        .order_by(Organization.moderator_verified_at.desc().nullslast(), Organization.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    orgs = list(result.scalars().unique().all())
    items: list[OrgPublic] = []
    for org in orgs:
        _, active = await get_org_counts(db, org.id)
        owner_name = await db.scalar(
            select(User.first_name)
            .join(OrgMember, OrgMember.user_id == User.id)
            .where(
                OrgMember.organization_id == org.id,
                OrgMember.is_owner.is_(True),
                OrgMember.status == MemberStatus.ACTIVE,
            )
        )
        items.append(org_public(org, active_listings_count=active, owner_name=owner_name))
    return items, int(total)


async def get_public_org(db: AsyncSession, slug: str) -> OrgPublic:
    org = await db.scalar(
        select(Organization)
        .where(
            Organization.slug == slug,
            Organization.status == OrgStatus.ACTIVE,
        )
        .options(
            selectinload(Organization.capabilities).selectinload(
                OrganizationCapability.capability
            )
        )
    )
    if org is None:
        raise AppError("Организация не найдена", status_code=404, code="organization_not_found")
    _, active = await get_org_counts(db, org.id)
    owner_name = await db.scalar(
        select(User.first_name)
        .join(OrgMember, OrgMember.user_id == User.id)
        .where(
            OrgMember.organization_id == org.id,
            OrgMember.is_owner.is_(True),
            OrgMember.status == MemberStatus.ACTIVE,
        )
    )
    return org_public(org, active_listings_count=active, owner_name=owner_name)
