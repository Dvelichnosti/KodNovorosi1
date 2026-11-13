import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from slugify import slugify as _slugify

from app.core.errors import AppError


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def slugify_text(value: str, fallback: str = "item") -> str:
    result = _slugify(value or "", max_length=120).strip("-")
    return result or f"{fallback}-{uuid.uuid4().hex[:8]}"


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) < 10 or len(digits) > 15:
        raise AppError(
            "Некорректный номер телефона",
            status_code=422,
            code="invalid_phone",
        )
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return "+" + digits


def normalize_inn(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) not in (10, 12):
        raise AppError(
            "ИНН должен содержать 10 цифр (юрлицо) или 12 цифр (ИП/самозанятый)",
            status_code=422,
            code="invalid_inn",
        )
    return digits


def clean_str(value: str | None, *, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if not result:
        return None
    if max_len and len(result) > max_len:
        raise AppError(
            f"Слишком длинное значение (максимум {max_len} символов)",
            status_code=422,
            code="value_too_long",
        )
    return result


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
