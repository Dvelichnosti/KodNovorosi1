from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.database import get_db
from app.core.errors import AppError
from app.core.permissions import ALL_PLATFORM_PERMISSIONS
from app.core.security import decode_token
from app.models.enums import UserStatus
from app.models.user import PlatformRole, User, UserPlatformRole

bearer = HTTPBearer(auto_error=False)
DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass
class AuthContext:
    user: User
    payload: dict


async def _resolve_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> AuthContext | None:
    if credentials is None or not credentials.credentials:
        return None
    payload = decode_token(credentials.credentials, expected_type="access")
    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(subject)
    except (TypeError, ValueError) as exc:
        raise AppError("Некорректный токен", status_code=401, code="invalid_token") from exc
    user = await db.get(User, user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=401, code="user_not_found")
    if user.status == UserStatus.BLOCKED:
        raise AppError(
            "Аккаунт заблокирован",
            status_code=403,
            code="account_blocked",
            details={"reason": user.blocked_reason},
        )
    request.state.auth = AuthContext(user=user, payload=payload)
    return AuthContext(user=user, payload=payload)


async def get_optional_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext | None:
    return await _resolve_auth(request, credentials, db)


async def get_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    auth = await _resolve_auth(request, credentials, db)
    if auth is None:
        raise AppError(
            "Требуется авторизация",
            status_code=401,
            code="unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth


async def get_current_user(auth: AuthContext = Depends(get_auth)) -> User:
    return auth.user


async def get_optional_user(
    auth: AuthContext | None = Depends(get_optional_auth),
) -> User | None:
    return auth.user if auth else None


def _platform_permission_key(user_id: uuid.UUID) -> str:
    return f"perms:platform:{user_id}"


async def invalidate_platform_permissions(user_id: uuid.UUID) -> None:
    await cache.delete(_platform_permission_key(user_id))


async def platform_permissions(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[set[str], list[str]]:
    cached = await cache.get_json(_platform_permission_key(user_id))
    if cached:
        return set(cached.get("permissions") or []), list(cached.get("roles") or [])
    result = await db.execute(
        select(PlatformRole)
        .join(UserPlatformRole, UserPlatformRole.role_id == PlatformRole.id)
        .where(UserPlatformRole.user_id == user_id)
    )
    roles = list(result.scalars().all())
    role_codes = [role.code for role in roles]
    permissions: set[str] = set()
    for role in roles:
        permissions.update(role.permissions or [])
    if "superadmin" in role_codes:
        permissions = set(ALL_PLATFORM_PERMISSIONS)
    await cache.set_json(
        _platform_permission_key(user_id),
        {"permissions": sorted(permissions), "roles": role_codes},
        ttl=300,
    )
    return permissions, role_codes


def require_platform_permission(permission: str) -> Callable:
    async def dependency(
        auth: AuthContext = Depends(get_auth),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        if not auth.payload.get("mfa"):
            raise AppError(
                "Для админ-API требуется подтверждение TOTP",
                status_code=403,
                code="mfa_required",
            )
        permissions, roles = await platform_permissions(db, auth.user.id)
        if permission not in permissions:
            raise AppError(
                "Недостаточно прав",
                status_code=403,
                code="permission_denied",
                details={"required": permission, "roles": roles},
            )
        return auth

    return dependency


def require_any_platform_permission(permissions: list[str]) -> Callable:
    async def dependency(
        auth: AuthContext = Depends(get_auth),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        if not auth.payload.get("mfa"):
            raise AppError(
                "Для админ-API требуется подтверждение TOTP",
                status_code=403,
                code="mfa_required",
            )
        granted, roles = await platform_permissions(db, auth.user.id)
        if not granted.intersection(permissions):
            raise AppError(
                "Недостаточно прав",
                status_code=403,
                code="permission_denied",
                details={"required_any": permissions, "roles": roles},
            )
        return auth

    return dependency
