import base64
import hashlib

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.errors import AppError


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            "Не удалось расшифровать TOTP-секрет",
            status_code=500,
            code="totp_decrypt_error",
        ) from exc


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_name,
        issuer_name=settings.totp_issuer,
    )


def verify_code(secret: str, code: str) -> bool:
    if not code:
        return False
    return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
