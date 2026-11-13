import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from app.core.config import settings
from app.core.errors import AppError

ALGORITHM = "HS256"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: uuid.UUID | str,
    *,
    mfa: bool = False,
    token_type: str = "access",
    ttl_minutes: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    now = utcnow()
    ttl = ttl_minutes if ttl_minutes is not None else settings.access_token_ttl_minutes
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "mfa": mfa,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, *, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AppError(
            "Срок действия токена истёк",
            status_code=401,
            code="token_expired",
        ) from exc
    except jwt.PyJWTError as exc:
        raise AppError(
            "Некорректный токен",
            status_code=401,
            code="invalid_token",
        ) from exc
    if payload.get("type") != expected_type:
        raise AppError(
            "Некорректный тип токена",
            status_code=401,
            code="invalid_token_type",
        )
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_url_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
