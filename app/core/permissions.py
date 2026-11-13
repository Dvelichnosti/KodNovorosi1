from typing import Final

ORG_PERMISSIONS: Final[dict[str, str]] = {
    "listing.create": "Создавать объявления",
    "listing.edit": "Редактировать объявления",
    "listing.publish": "Публиковать объявления",
    "listing.delete": "Удалять объявления",
    "listing.view_stats": "Смотреть статистику объявлений",
    "listing.promote": "Продвигать объявления",
    "org.edit_profile": "Редактировать профиль организации",
    "org.manage_contacts": "Управлять контактами организации",
    "org.manage_members": "Управлять сотрудниками",
    "org.manage_roles": "Управлять ролями",
    "review.reply": "Отвечать на отзывы",
    "billing.view": "Смотреть тариф и лимиты",
    "billing.manage": "Управлять тарифом",
}

ALL_ORG_PERMISSIONS: Final[list[str]] = list(ORG_PERMISSIONS)

PLATFORM_PERMISSIONS: Final[dict[str, str]] = {
    "users.view": "Просмотр пользователей",
    "users.block": "Блокировка пользователей",
    "orgs.verify": "Верификация организаций",
    "listings.moderate": "Модерация объявлений",
    "complaints.handle": "Обработка жалоб",
    "catalog.manage": "Управление каталогом",
    "roles.manage_platform": "Управление платформенными ролями",
    "plans.manage": "Управление тарифами",
    "audit.view": "Просмотр аудита",
    "settings.manage": "Управление настройками",
}

ALL_PLATFORM_PERMISSIONS: Final[list[str]] = list(PLATFORM_PERMISSIONS)

DEFAULT_ORG_ROLES: Final[list[dict]] = [
    {
        "name": "Менеджер объявлений",
        "permissions": [
            "listing.create",
            "listing.edit",
            "listing.publish",
            "listing.delete",
            "listing.view_stats",
            "listing.promote",
            "review.reply",
        ],
    },
    {
        "name": "Редактор профиля",
        "permissions": [
            "org.edit_profile",
            "org.manage_contacts",
            "review.reply",
        ],
    },
    {
        "name": "Только просмотр",
        "permissions": [
            "listing.view_stats",
            "billing.view",
        ],
    },
]

PLATFORM_ROLE_TEMPLATES: Final[list[dict]] = [
    {
        "code": "superadmin",
        "name": "Суперадмин",
        "permissions": ALL_PLATFORM_PERMISSIONS,
        "is_system": True,
    },
    {
        "code": "moderator",
        "name": "Модератор",
        "permissions": [
            "users.view",
            "orgs.verify",
            "listings.moderate",
            "complaints.handle",
            "catalog.manage",
            "audit.view",
        ],
        "is_system": True,
    },
    {
        "code": "support",
        "name": "Поддержка",
        "permissions": [
            "users.view",
            "orgs.verify",
            "complaints.handle",
        ],
        "is_system": True,
    },
]


def is_subset(requested: list[str], granted: set[str]) -> bool:
    return set(requested).issubset(granted)
