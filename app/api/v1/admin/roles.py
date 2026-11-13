from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select

from app.api.deps import DB, AuthContext, require_platform_permission
from app.core.audit import write_audit
from app.core.errors import AppError
from app.core.permissions import PLATFORM_PERMISSIONS
from app.core.utils import client_ip
from app.models.user import PlatformRole, UserPlatformRole
from app.schemas.admin import (
    PlatformRoleCreate,
    PlatformRoleOut,
    PlatformRoleUpdate,
)
from app.schemas.common import Message

router = APIRouter(prefix="/platform-roles", tags=["admin: roles"])


def _validate_permissions(permissions: list[str]) -> list[str]:
    unknown = [item for item in permissions if item not in PLATFORM_PERMISSIONS]
    if unknown:
        raise AppError(
            "Неизвестные платформенные разрешения",
            status_code=422,
            code="unknown_permission",
            details={"unknown": unknown, "allowed": sorted(PLATFORM_PERMISSIONS)},
        )
    return list(dict.fromkeys(permissions))


async def _role_out(db: DB, role: PlatformRole) -> PlatformRoleOut:
    count = await db.scalar(
        select(func.count(UserPlatformRole.user_id)).where(
            UserPlatformRole.role_id == role.id
        )
    )
    return PlatformRoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        permissions=role.permissions or [],
        is_system=role.is_system,
        users_count=int(count or 0),
    )


@router.get("", response_model=list[PlatformRoleOut])
async def list_roles(
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> list[PlatformRoleOut]:
    result = await db.execute(select(PlatformRole).order_by(PlatformRole.code))
    return [await _role_out(db, role) for role in result.scalars().all()]


@router.post("", response_model=PlatformRoleOut, status_code=201)
async def create_role(
    data: PlatformRoleCreate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> PlatformRoleOut:
    existing = await db.scalar(select(PlatformRole.id).where(PlatformRole.code == data.code))
    if existing:
        raise AppError("Роль с таким кодом уже существует", status_code=409, code="role_exists")
    role = PlatformRole(
        code=data.code,
        name=data.name.strip(),
        permissions=_validate_permissions(data.permissions),
        is_system=False,
    )
    db.add(role)
    await db.flush()
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="platform_role.create",
        entity_type="platform_role",
        entity_id=role.id,
        payload={"code": data.code, "permissions": data.permissions},
        ip=client_ip(request),
    )
    await db.commit()
    await db.refresh(role)
    return await _role_out(db, role)


@router.patch("/{role_id}", response_model=PlatformRoleOut)
async def update_role(
    role_id: uuid.UUID,
    data: PlatformRoleUpdate,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> PlatformRoleOut:
    role = await db.get(PlatformRole, role_id)
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    if data.name is not None:
        role.name = data.name.strip()
    if data.permissions is not None:
        role.permissions = _validate_permissions(data.permissions)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="platform_role.update",
        entity_type="platform_role",
        entity_id=role.id,
        payload=data.model_dump(exclude_unset=True),
        ip=client_ip(request),
    )
    await db.commit()
    await db.refresh(role)
    return await _role_out(db, role)


@router.delete("/{role_id}", response_model=Message)
async def delete_role(
    role_id: uuid.UUID,
    request: Request,
    auth: AuthContext = Depends(require_platform_permission("roles.manage_platform")),
    db: DB = None,
) -> Message:
    role = await db.get(PlatformRole, role_id)
    if role is None:
        raise AppError("Роль не найдена", status_code=404, code="role_not_found")
    if role.is_system:
        raise AppError(
            "Системную платформенную роль нельзя удалить",
            status_code=409,
            code="system_role_immutable",
        )
    assigned = await db.scalar(
        select(func.count(UserPlatformRole.user_id)).where(
            UserPlatformRole.role_id == role.id
        )
    )
    if assigned:
        raise AppError(
            "Роль назначена пользователям. Сначала снимите её.",
            status_code=409,
            code="role_in_use",
            details={"users_count": int(assigned)},
        )
    await db.delete(role)
    await write_audit(
        db,
        actor_id=auth.user.id,
        action="platform_role.delete",
        entity_type="platform_role",
        entity_id=role_id,
        payload={"code": role.code},
        ip=client_ip(request),
    )
    await db.commit()
    return Message(message="Роль удалена")
