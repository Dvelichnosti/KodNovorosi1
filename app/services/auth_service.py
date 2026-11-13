from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.core.security import create_access_token, hash_token, new_refresh_token, new_url_token
from app.core.telegram import telegram_bot
from app.core.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_secret,
    provisioning_uri,
    verify_code,
)
from app.core.utils import normalize_phone
from app.models.auth import LoginSession, RefreshToken
from app.models.enums import LoginStatus, UserStatus
from app.models.user import PlatformRole, TotpSecret, User, UserPlatformRole
from app.schemas.auth import TokenPair
from app.services.serializers import user_me


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_platform_role_codes(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await db.execute(
        select(PlatformRole.code)
        .join(UserPlatformRole, UserPlatformRole.role_id == PlatformRole.id)
        .where(UserPlatformRole.user_id == user_id)
    )
    return list(result.scalars().all())


async def is_platform_user(db: AsyncSession, user_id: uuid.UUID) -> bool:
    return bool(await get_platform_role_codes(db, user_id))


async def get_totp_secret(db: AsyncSession, user_id: uuid.UUID) -> TotpSecret | None:
    return await db.get(TotpSecret, user_id)


async def start_telegram_login(
    db: AsyncSession,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[LoginSession, str]:
    raw_token = new_url_token(32)
    session = LoginSession(
        token_hash=hash_token(raw_token),
        status=LoginStatus.PENDING,
        expires_at=_now() + timedelta(minutes=settings.login_session_ttl_minutes),
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session, raw_token


async def _get_or_create_user(
    db: AsyncSession,
    *,
    telegram_id: int,
    phone: str | None,
    first_name: str | None,
    last_name: str | None,
    username: str | None,
) -> User:
    user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
    if user is None and phone:
        user = await db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(
            telegram_id=telegram_id,
            phone=phone,
            first_name=first_name,
            last_name=last_name,
            telegram_username=username,
            notification_settings={
                "new_listing_moderated": True,
                "new_complaint": True,
                "new_invitation": True,
                "listing_expiring": True,
            },
            last_login_at=_now(),
        )
        if phone:
            user.phone_verified_at = _now()
        db.add(user)
        await db.flush()
        return user

    if user.status == UserStatus.BLOCKED:
        raise AppError(
            "Аккаунт заблокирован",
            status_code=403,
            code="account_blocked",
            details={"reason": user.blocked_reason},
        )
    user.telegram_id = telegram_id
    if username:
        user.telegram_username = username
    if first_name:
        user.first_name = first_name
    if last_name:
        user.last_name = last_name
    if phone:
        user.phone = phone
        user.phone_verified_at = _now()
    user.last_login_at = _now()
    await db.flush()
    return user


async def confirm_telegram_login(
    db: AsyncSession,
    *,
    token: str,
    telegram_id: int,
    phone: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    chat_id: int | None = None,
) -> LoginSession:
    session = await db.scalar(
        select(LoginSession).where(LoginSession.token_hash == hash_token(token))
    )
    if session is None:
        raise AppError("Сессия входа не найдена", status_code=404, code="login_not_found")
    return await confirm_login_session(
        db,
        session,
        telegram_id=telegram_id,
        phone=phone,
        first_name=first_name,
        last_name=last_name,
        username=username,
        chat_id=chat_id,
    )


async def confirm_login_session(
    db: AsyncSession,
    session: LoginSession,
    *,
    telegram_id: int,
    phone: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
    username: str | None = None,
    chat_id: int | None = None,
) -> LoginSession:
    if session.status == LoginStatus.CONSUMED:
        raise AppError("Сессия уже использована", status_code=410, code="login_used")
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if session.status == LoginStatus.EXPIRED or expires_at < _now():
        session.status = LoginStatus.EXPIRED
        await db.commit()
        raise AppError("Сессия входа истекла", status_code=410, code="login_expired")
    if session.status == LoginStatus.CONFIRMED:
        return session

    normalized_phone = normalize_phone(phone)
    user = await _get_or_create_user(
        db,
        telegram_id=telegram_id,
        phone=normalized_phone,
        first_name=first_name,
        last_name=last_name,
        username=username,
    )
    session.status = LoginStatus.CONFIRMED
    session.telegram_id = telegram_id
    session.phone = normalized_phone
    session.first_name = first_name
    session.last_name = last_name
    session.username = username
    session.chat_id = chat_id
    session.user_id = user.id
    session.confirmed_at = _now()
    await db.commit()
    await db.refresh(session)

    # Auto-accept invitations addressed to this Telegram account.
    from app.services import org_service

    try:
        await org_service.accept_pending_invites(db, user)
    except Exception:
        await db.rollback()
    return session


async def issue_token_pair(
    db: AsyncSession,
    user: User,
    *,
    mfa: bool = False,
    ip: str | None = None,
    user_agent: str | None = None,
    family_id: uuid.UUID | None = None,
) -> TokenPair:
    raw_refresh = new_refresh_token()
    refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family_id=family_id or uuid.uuid4(),
        mfa=mfa,
        expires_at=_now() + timedelta(days=settings.refresh_token_ttl_days),
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(refresh)
    await db.flush()

    access = create_access_token(user.id, mfa=mfa)
    platform_codes = await get_platform_role_codes(db, user.id)
    totp_secret = await get_totp_secret(db, user.id)
    return TokenPair(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
        requires_totp=bool(platform_codes) and not mfa,
        totp_enabled=bool(totp_secret and totp_secret.enabled),
        user=user_me(user),
    )


async def poll_telegram_login(
    db: AsyncSession,
    *,
    token: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, TokenPair | None]:
    session = await db.scalar(
        select(LoginSession).where(LoginSession.token_hash == hash_token(token))
    )
    if session is None:
        raise AppError("Сессия входа не найдена", status_code=404, code="login_not_found")
    if session.status == LoginStatus.CONSUMED:
        raise AppError("Сессия уже использована", status_code=410, code="login_used")
    if session.status == LoginStatus.EXPIRED or (
        session.status == LoginStatus.PENDING and session.expires_at < _now()
    ):
        session.status = LoginStatus.EXPIRED
        await db.commit()
        raise AppError("Сессия входа истекла", status_code=410, code="login_expired")
    if session.status == LoginStatus.PENDING:
        return "pending", None
    if session.user_id is None:
        raise AppError("Пользователь не найден", status_code=409, code="login_incomplete")

    user = await db.get(User, session.user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=404, code="user_not_found")
    if user.status == UserStatus.BLOCKED:
        raise AppError(
            "Аккаунт заблокирован",
            status_code=403,
            code="account_blocked",
            details={"reason": user.blocked_reason},
        )

    tokens = await issue_token_pair(db, user, mfa=False, ip=ip, user_agent=user_agent)
    session.status = LoginStatus.CONSUMED
    session.consumed_at = _now()
    await db.commit()
    return "confirmed", tokens


async def rotate_refresh_token(
    db: AsyncSession,
    *,
    raw_token: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    row = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if row is None:
        raise AppError(
            "Refresh-токен не найден",
            status_code=401,
            code="invalid_refresh_token",
        )
    if row.revoked_at is not None:
        # A revoked token was reused: revoke the whole token family.
        await db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == row.family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=_now())
        )
        await db.commit()
        raise AppError(
            "Refresh-токен уже использован. Все сессии отозваны.",
            status_code=401,
            code="refresh_reuse_detected",
        )
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < _now():
        raise AppError("Refresh-токен истёк", status_code=401, code="refresh_expired")

    user = await db.get(User, row.user_id)
    if user is None:
        raise AppError("Пользователь не найден", status_code=401, code="user_not_found")
    if user.status == UserStatus.BLOCKED:
        raise AppError(
            "Аккаунт заблокирован",
            status_code=403,
            code="account_blocked",
            details={"reason": user.blocked_reason},
        )

    raw_refresh = new_refresh_token()
    new_row = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family_id=row.family_id,
        mfa=row.mfa,
        expires_at=_now() + timedelta(days=settings.refresh_token_ttl_days),
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
    )
    db.add(new_row)
    await db.flush()

    row.revoked_at = _now()
    row.replaced_by_id = new_row.id
    await db.commit()

    access = create_access_token(user.id, mfa=row.mfa)
    platform_codes = await get_platform_role_codes(db, user.id)
    totp_secret = await get_totp_secret(db, user.id)
    return TokenPair(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_ttl_minutes * 60,
        requires_totp=bool(platform_codes) and not row.mfa,
        totp_enabled=bool(totp_secret and totp_secret.enabled),
        user=user_me(user),
    )


async def revoke_refresh_token(db: AsyncSession, raw_token: str) -> None:
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if row and row.revoked_at is None:
        row.revoked_at = _now()
        await db.commit()


async def revoke_all_tokens(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await db.commit()


async def setup_totp(db: AsyncSession, user: User) -> tuple[str, str]:
    if not await is_platform_user(db, user.id):
        raise AppError(
            "TOTP доступен только платформенным ролям",
            status_code=403,
            code="not_platform_user",
        )
    existing = await get_totp_secret(db, user.id)
    if existing and existing.enabled:
        raise AppError("TOTP уже включён", status_code=409, code="totp_already_enabled")
    secret = generate_secret()
    if existing is None:
        existing = TotpSecret(user_id=user.id, secret_encrypted=encrypt_secret(secret))
        db.add(existing)
    else:
        existing.secret_encrypted = encrypt_secret(secret)
        existing.enabled = False
        existing.confirmed_at = None
    await db.commit()
    account = user.telegram_username or user.full_name or str(user.id)
    return secret, provisioning_uri(secret, f"{settings.totp_issuer}:{account}")


async def enable_totp(
    db: AsyncSession,
    user: User,
    *,
    code: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    secret_row = await get_totp_secret(db, user.id)
    if secret_row is None:
        raise AppError("Сначала создайте TOTP-секрет", status_code=409, code="totp_not_setup")
    secret = decrypt_secret(secret_row.secret_encrypted)
    if not verify_code(secret, code):
        raise AppError("Неверный код TOTP", status_code=400, code="invalid_totp_code")
    secret_row.enabled = True
    secret_row.confirmed_at = _now()
    await db.commit()
    return await issue_token_pair(db, user, mfa=True, ip=ip, user_agent=user_agent)


async def verify_totp(
    db: AsyncSession,
    user: User,
    *,
    code: str,
    ip: str | None = None,
    user_agent: str | None = None,
) -> TokenPair:
    secret_row = await get_totp_secret(db, user.id)
    if secret_row is None or not secret_row.enabled:
        raise AppError("TOTP не настроен", status_code=409, code="totp_not_enabled")
    secret = decrypt_secret(secret_row.secret_encrypted)
    if not verify_code(secret, code):
        raise AppError("Неверный код TOTP", status_code=400, code="invalid_totp_code")
    return await issue_token_pair(db, user, mfa=True, ip=ip, user_agent=user_agent)


async def telegram_login_url(db: AsyncSession) -> tuple[str, str, int]:
    session, token = await start_telegram_login(db, ip=None, user_agent=None)
    return token, telegram_bot.login_link(token), settings.login_session_ttl_minutes * 60
