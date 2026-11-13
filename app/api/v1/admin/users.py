from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select

from app.api.deps import (
    DB,
    AuthContext,
    invalidate_platform_permissions,
    platform_permissions,
    require_platform_permission,
)
from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.utils import client_ip
from app.models.enums import MemberStatus, UserStatus
from app.models.organization import OrgMember
from app.models.user import PlatformRole, User, UserPlatformRole
from app.schemas.admin import (
    AdminUserOut,
    AssignPlatformRoleIn,
    BlockUserIn,
)
from app.schemas.common import Message, Page
from app.services import auth_service
from app.services.serializers import admin_user_out

router = APIRouter(prefix="/users", tags=["admin: users"])


async def _org_counts(db: DB, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    result = await db.execute(
        select(OrgMember.user_id, func.count(OrgMember.id))
        .where(
            OrgMember.user_id.in_(user_ids),
            OrgMember.status == MemberStatus.ACTIVE,
        )
        .group_by(OrgMember.user_id)
    )
    return {user_id: count for user_id, count in result.all()}


@router.get("", response_model=Page[AdminUserOut])
async def list_users(
    q: str | None = Query(default=None, max_length=200),
    status_filter: UserStatus | None = Query(default=None, alias="status"),
    role: str | None = Query(default=None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_platform_permission("users.view")),
    db: DB = None,
) -> Page[AdminUserOut]:
    query = select(User)
    if q:
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                User.phone.ilike(pattern),
                User.email.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.telegram_username.ilike(pattern),
            )
        )
    if status_filter:
        query = query.where(User.status == status_filter)
    if role:
        query = query.where(
            User.id.in_(
                select(UserPlatformRole.user_id)
                .join(PlatformRole, PlatformRole.id == UserPlatformRole.role_id)
                .where(PlatformRole.code == role)
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    )
    users = list(result.scalars().unique().all())
    counts = await _org_counts(db, [user.id for user in users])
    items = [admin_user_out(user, organizations_count=counts.get(user.id, 0)) for user in users]
    return Page.build(items, int(total), page, per_page)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(
    user_id: uuid.UUID,
    auth: AuthContext = Depends(require_platform_permission("users.view")),
    db: DB = None,
) -> AdminUserOut:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=404, code="user_not_found")
    counts = await _org_counts(db, [user.id])
    return admin_user_out(user, organizations_count=counts.get(user.id, 0))


@router.post("/{user_id}/block", response_model=Message)
async def block_user(
    user_id: uuid.UUID,
    data: BlockUserIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("users.block")),
    db: DB = None,
) -> Message:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=404, code="user_not_found")
    if user.id == auth.user.id:
        raise AppError("Нельзя заблокировать себя", status_code=409, code="cannot_block_self")
    target_permissions, target_roles = await platform_permissions(db, user.id)
    actor_permissions, actor_roles = await platform_permissions(db, auth.user.id)
    if "superadmin" in target_roles and "superadmin" not in actor_roles:
        raise AppError(
            "Только суперадмин может заблокировать суперадмина",
            status_code=403,
            code="cannot_block_superadmin",
        )
    user.status = UserStatus.BLOCKED
    user.blocked_reason = data.reason
    user.blocked_at = datetime.now(timezone.utc)
    await auth_service.revoke_all_tokens(db, user.id)
    await invalidate_platform_permissions(user.id)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="user.block",
        entity_type="user",
        entity_id=user.id,
        payload={"reason": data.reason},
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Пользователь заблокирован")


@router.post("/{user_id}/unblock", response_model=Message)
async def unblock_user(
    user_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("users.block")),
    db: DB = None,
) -> Message:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=404, code="user_not_found")
    user.status = UserStatus.ACTIVE
    user.blocked_reason = None
    user.blocked_at = None
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="user.unblock",
        entity_type="user",
        entity_id=user.id,
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Пользователь разблокирован")


@router.post("/{user_id}/platform-roles", response_model=Message)
async def assign_platform_role(
    user_id: uuid.UUID,
    data: AssignPlatformRoleIn,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> Message:
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=404, code="user_not_found")
    role = await db.get(PlatformRole, data.role_id)
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    existing = await db.scalar(
        select(UserPlatformRole).where(
            UserPlatformRole.user_id == user.id,
            UserPlatformRole.role_id == role.id,
        )
    )
    if existing is None:
        db.add(
            UserPlatformRole(
                user_id=user.id,
                role_id=role.id,
                assigned_by=auth.user.id,
            )
        )
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="platform_role.assign",
        entity_type="user",
        entity_id=user.id,
        payload={"role": role.code},
        ip=client_ip(request),
    )
    await db.commit()
    await invalidate_platform_permissions(user.id)
    return Message(message="Роль назначена")


@router.delete("/{user_id}/platform-roles/{role_id}", response_model=Message)
async def revoke_platform_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> Message:
    link = await db.scalar(
        select(UserPlatformRole).where(
            UserPlatformRole.user_id == user_id,
            UserPlatformRole.role_id == role_id,
        )
    )
    if link is None:
        raise AppError("Роль не назначена", status_code=404, code="role_not_assigned")
    role = await db.get(PlatformRole, role_id)
    if role and role.code == "superadmin":
        count = await db.scalar(
            select(func.count(UserPlatformRole.user_id))
            .join(PlatformRole, PlatformRole.id == UserPlatformRole.role_id)
            .where(PlatformRole.code == "superadmin")
        )
        if int(count or 0) <= 1:
            raise AppError(
                "Нельзя снять роль у последнего суперадмина",
                status_code=409,
                code="last_superadmin",
            )
    await db.delete(link)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="platform_role.revoke",
        entity_type="user",
        entity_id=user_id,
        payload={"role_id": str(role_id)},
        ip=client_ip(request),
    )
    await db.commit()
    await invalidate_platform_permissions(user_id)
    return Message(message="Роль снята")
