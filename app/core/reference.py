from typing import Any, Final

REGIONS: Final[dict[str, str]] = {
    "dnr": "ДНР",
    "lnr": "ЛНР",
    "kherson": "Херсонская область",
    "zaporozhye": "Запорожская область",
}

ORG_TYPES: Final[dict[str, str]] = {
    "legal_entity": "Юридическое лицо",
    "sole_proprietor": "ИП",
    "self_employed": "Самозанятый",
}

ORG_TYPE_INN_LENGTH: Final[dict[str, int]] = {
    "legal_entity": 10,
    "sole_proprietor": 12,
    "self_employed": 12,
}

VERIFICATION_LEVELS: Final[dict[str, str]] = {
    "none": "Без верификации",
    "phone": "Телефон подтверждён",
    "inn": "ИНН проверен",
    "moderator": "Проверен модератором",
}

LISTING_TYPES: Final[dict[str, str]] = {
    "sale": "Продам",
    "rent_out": "Сдам",
    "wanted_buy": "Куплю",
    "wanted_rent": "Сниму",
    "service_offer": "Оказываю услуги",
    "service_wanted": "Ищу подрядчика",
    "tender": "Тендер",
    "partnership": "Партнёрство, франшиза",
}

LISTING_STATUSES: Final[dict[str, str]] = {
    "draft": "Черновик",
    "pending": "На модерации",
    "active": "Активно",
    "rejected": "Отклонено",
    "archived": "В архиве",
    "expired": "Истекло",
    "blocked": "Заблокировано",
}

COMPLAINT_REASONS: Final[dict[str, str]] = {
    "spam": "Спам или дубль",
    "fraud": "Мошенничество",
    "wrong_category": "Неверная категория",
    "prohibited": "Запрещённый товар или услуга",
    "offensive": "Оскорбительный контент",
    "other": "Другое",
}

COMPLAINT_STATUSES: Final[dict[str, str]] = {
    "new": "Новая",
    "in_review": "В работе",
    "resolved": "Решена",
    "rejected": "Отклонена",
}

ATTRIBUTE_TYPES: Final[dict[str, str]] = {
    "string": "Строка",
    "number": "Число",
    "enum": "Один вариант",
    "multi_enum": "Несколько вариантов",
    "bool": "Да/Нет",
    "range": "Диапазон",
    "date": "Дата",
}

DEFAULT_CAPABILITIES: Final[list[dict[str, Any]]] = [
    {
        "code": "transport",
        "name": "Перевозки",
        "param_schema": {
            "body_types": "multi_enum",
            "capacity_t": "number",
            "work_zones": "string",
        },
    },
    {
        "code": "delivery",
        "name": "Доставка",
        "param_schema": {"zones": "string", "same_day": "bool"},
    },
    {
        "code": "installation",
        "name": "Монтаж",
        "param_schema": {"equipment_types": "string"},
    },
    {
        "code": "rent",
        "name": "Аренда",
        "param_schema": {"min_term_days": "number"},
    },
    {
        "code": "vat",
        "name": "Работа с НДС",
        "param_schema": {},
    },
    {
        "code": "government_order",
        "name": "Работа с госзаказом",
        "param_schema": {},
    },
]
