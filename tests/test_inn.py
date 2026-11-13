from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.core.inn import check_inn
from app.core.utils import normalize_phone


@pytest.mark.parametrize(
    "inn",
    [
        "7707083893",
        "500100732259",
    ],
)
def test_valid_inn_checksum(inn: str) -> None:
    result = check_inn(inn)
    assert result.valid, result.reason


def test_invalid_inn_checksum() -> None:
    result = check_inn("7707083894")
    assert not result.valid
    assert "контрольной суммы" in (result.reason or "")


def test_inn_expected_length() -> None:
    result = check_inn("7707083893", expected_length=12)
    assert not result.valid
    assert "12" in (result.reason or "")


def test_normalize_phone() -> None:
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("+7 999 123 45 67") == "+79991234567"
    assert normalize_phone(None) is None


def test_normalize_phone_rejects_garbage() -> None:
    with pytest.raises(AppError) as exc:
        normalize_phone("123")
    assert exc.value.code == "invalid_phone"
