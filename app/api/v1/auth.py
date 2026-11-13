from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from app.api.deps import DB, AuthContext, get_auth
from app.core.config import settings
from app.core.errors import AppError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_token
from app.core.utils import client_ip
from app.models.user import TotpSecret
from app.schemas.auth import (
    AuthProviderOut,
    AuthProvidersOut,
    LogoutIn,
    RefreshIn,
    TelegramDevConfirmIn,
    TelegramPollIn,
    TelegramPollOut,
    TelegramStartOut,
    TokenPair,
    TotpCodeIn,
    TotpSetupOut,
    TotpStatusOut,
)
from app.schemas.common import Message
from app.schemas.user import UserMe
from app.services import auth_service
from app.services.serializers import user_me

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.post("/telegram/start", response_model=TelegramStartOut)
async def telegram_start(request: Request, db: DB) -> TelegramStartOut:
    ip = client_ip(request)
    await enforce_rate_limit(
        f"login-start:{ip}",
        settings.login_start_rate_limit,
        settings.login_start_rate_window,
    )
    session, token = await auth_service.start_telegram_login(
        db,
        ip=ip,
        user_agent=_user_agent(request),
    )
    return TelegramStartOut(
        token=token,
        login_url=auth_service.telegram_bot.login_link(token),
        expires_in=settings.login_session_ttl_minutes * 60,
    )


@router.post("/telegram/poll", response_model=TelegramPollOut)
async def telegram_poll(request: Request, data: TelegramPollIn, db: DB) -> TelegramPollOut:
    ip = client_ip(request)
    await enforce_rate_limit(
        f"login-poll:{hash_token(data.token)[:24]}:{ip}",
        settings.login_poll_rate_limit,
        settings.login_poll_rate_window,
    )
    status_value, tokens = await auth_service.poll_telegram_login(
        db,
        token=data.token,
        ip=ip,
        user_agent=_user_agent(request),
    )
    return TelegramPollOut(status=status_value, tokens=tokens)


@router.post("/telegram/dev-confirm", response_model=Message, include_in_schema=False)
async def telegram_dev_confirm(data: TelegramDevConfirmIn, db: DB) -> Message:
    if settings.is_production or not settings.debug:
        raise AppError("Маршрут недоступен", status_code=404, code="not_found")
    await auth_service.confirm_telegram_login(
        db,
        token=data.token,
        telegram_id=data.telegram_id,
        phone=data.phone,
        first_name=data.first_name,
        last_name=data.last_name,
        username=data.username,
    )
    return Message(message="Вход подтверждён")


@router.post("/refresh", response_model=TokenPair)
async def refresh(request: Request, data: RefreshIn, db: DB) -> TokenPair:
    await enforce_rate_limit(
        f"refresh:{client_ip(request)}",
        settings.login_poll_rate_limit,
        settings.login_poll_rate_window,
    )
    return await auth_service.rotate_refresh_token(
        db,
        raw_token=data.refresh_token,
        ip=client_ip(request),
        user_agent=_user_agent(request),
    )


@router.post("/logout", response_model=Message)
async def logout(data: LogoutIn, db: DB) -> Message:
    await auth_service.revoke_refresh_token(db, data.refresh_token)
    return Message(message="Выход выполнен")


@router.post("/logout-all", response_model=Message)
async def logout_all(auth: AuthContext = Depends(get_auth), db: DB = None) -> Message:
    await auth_service.revoke_all_tokens(db, auth.user.id)
    return Message(message="Все сессии отозваны")


@router.get("/me", response_model=UserMe)
async def me(auth: AuthContext = Depends(get_auth)) -> UserMe:
    return user_me(auth.user)


@router.get("/providers", response_model=AuthProvidersOut)
async def providers() -> AuthProvidersOut:
    return AuthProvidersOut(
        providers=[
            AuthProviderOut(
                code="telegram",
                name="Telegram",
                enabled=True,
            ),
            AuthProviderOut(code="sms", name="СМС", enabled=False),
            AuthProviderOut(code="email", name="Email", enabled=False),
        ]
    )


@router.post("/totp/setup", response_model=TotpSetupOut)
async def totp_setup(auth: AuthContext = Depends(get_auth), db: DB = None) -> TotpSetupOut:
    secret, uri = await auth_service.setup_totp(db, auth.user)
    return TotpSetupOut(secret=secret, otpauth_url=uri, issuer=settings.totp_issuer)


@router.post("/totp/enable", response_model=TokenPair)
async def totp_enable(
    request: Request,
    data: TotpCodeIn,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> TokenPair:
    await enforce_rate_limit(f"totp:{auth.user.id}", 10, 60)
    return await auth_service.enable_totp(
        db,
        auth.user,
        code=data.code,
        ip=client_ip(request),
        user_agent=_user_agent(request),
    )


@router.post("/totp/verify", response_model=TokenPair)
async def totp_verify(
    request: Request,
    data: TotpCodeIn,
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> TokenPair:
    await enforce_rate_limit(f"totp:{auth.user.id}", 10, 60)
    return await auth_service.verify_totp(
        db,
        auth.user,
        code=data.code,
        ip=client_ip(request),
        user_agent=_user_agent(request),
    )


@router.get("/totp/status", response_model=TotpStatusOut)
async def totp_status(auth: AuthContext = Depends(get_auth), db: DB = None) -> TotpStatusOut:
    secret = await db.scalar(select(TotpSecret).where(TotpSecret.user_id == auth.user.id))
    return TotpStatusOut(
        enabled=bool(secret and secret.enabled),
        confirmed_at=secret.confirmed_at if secret else None,
    )
