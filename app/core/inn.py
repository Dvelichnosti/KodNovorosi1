import re
from dataclasses import dataclass


@dataclass(slots=True)
class InnCheckResult:
    inn: str
    valid: bool
    reason: str | None = None


def _digits_only(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _check_10(inn: str) -> bool:
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    control = sum(int(inn[i]) * weights[i] for i in range(9)) % 11 % 10
    return control == int(inn[9])


def _check_12(inn: str) -> bool:
    weights_11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    control_11 = sum(int(inn[i]) * weights_11[i] for i in range(10)) % 11 % 10
    if control_11 != int(inn[10]):
        return False
    weights_12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    control_12 = sum(int(inn[i]) * weights_12[i] for i in range(11)) % 11 % 10
    return control_12 == int(inn[11])


def check_inn(value: str, expected_length: int | None = None) -> InnCheckResult:
    inn = _digits_only(value)
    if len(inn) not in (10, 12):
        return InnCheckResult(
            inn=inn,
            valid=False,
            reason="ИНН должен содержать 10 цифр (юрлицо) или 12 цифр (ИП/самозанятый)",
        )
    if expected_length and len(inn) != expected_length:
        return InnCheckResult(
            inn=inn,
            valid=False,
            reason=f"Для выбранного типа организации нужен ИНН из {expected_length} цифр",
        )
    valid = _check_10(inn) if len(inn) == 10 else _check_12(inn)
    if not valid:
        return InnCheckResult(inn=inn, valid=False, reason="ИНН не прошёл проверку контрольной суммы")
    return InnCheckResult(inn=inn, valid=True)


class InnVerifier:
    """Interface for external INN verification (FNS / DaData).

    The MVP uses the checksum implementation. A real provider can be plugged in
    without changing the organization service.
    """

    async def verify(self, inn: str) -> InnCheckResult:  # pragma: no cover - interface
        raise NotImplementedError


class ChecksumInnVerifier(InnVerifier):
    async def verify(self, inn: str) -> InnCheckResult:
        return check_inn(inn)


def get_inn_verifier() -> InnVerifier:
    return ChecksumInnVerifier()
