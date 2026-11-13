from __future__ import annotations

from typing import Any

CATEGORY_TREE: dict[str, list[str]] = {
    "Оборудование": [
        "производственное",
        "пищевое и пекарное",
        "торговое и холодильное",
        "строительное",
        "складское и погрузчики",
        "сельскохозяйственное",
        "медицинское и косметологическое",
        "для общепита",
        "офисное и IT",
        "энергетика (генераторы, солнечные панели)",
        "б/у оборудование",
    ],
    "Коммерческая недвижимость": [
        "офисы",
        "торговые помещения",
        "склады",
        "производственные помещения",
        "земля коммерческого назначения",
        "помещения под общепит",
        "коворкинги и рабочие места",
    ],
    "Транспорт и спецтехника": [
        "грузовики",
        "фургоны и малый коммерческий",
        "прицепы",
        "спецтехника",
        "автобусы",
        "запчасти и шины",
        "аренда с водителем",
    ],
    "Реклама и маркетинг": [
        "рекламные агентства",
        "SMM и таргет",
        "типографии и полиграфия",
        "наружная реклама",
        "сувенирная продукция",
        "веб-студии и SEO",
        "дизайн и брендинг",
        "фото и видео",
    ],
    "Услуги для бизнеса": [
        "юридические",
        "бухгалтерия и налоги",
        "консалтинг и помощь с регистрацией",
        "IT и разработка",
        "строительство и ремонт",
        "монтаж и обслуживание оборудования",
        "клининг",
        "охрана",
        "кадры и обучение",
        "сертификация и лицензии",
        "переводы",
    ],
    "Логистика и перевозки": [
        "грузоперевозки",
        "грузчики",
        "спецперевозки и негабарит",
        "курьерская доставка",
        "склады ответхранения",
        "экспедирование",
    ],
    "Товары и сырьё (опт)": [
        "продукты питания",
        "стройматериалы",
        "металлопрокат",
        "упаковка",
        "сельхозпродукция",
        "одежда и текстиль",
        "хозтовары",
        "топливо и ГСМ",
    ],
    "Готовый бизнес и франшизы": [
        "готовый бизнес",
        "франшизы",
        "поиск инвестора и партнёра",
    ],
}

ROOT_SLUGS: dict[str, str] = {
    "Оборудование": "oborudovanie",
    "Коммерческая недвижимость": "kommercheskaya-nedvizhimost",
    "Транспорт и спецтехника": "transport-i-spectehnika",
    "Реклама и маркетинг": "reklama-i-marketing",
    "Услуги для бизнеса": "uslugi-dlya-biznesa",
    "Логистика и перевозки": "logistika-i-perevozki",
    "Товары и сырьё (опт)": "tovary-i-syryo-opt",
    "Готовый бизнес и франшизы": "gotovyy-biznes-i-franshizy",
}

ALLOWED_TYPES: dict[str, list[str]] = {
    "oborudovanie": ["sale", "rent_out", "wanted_buy", "wanted_rent"],
    "kommercheskaya-nedvizhimost": ["rent_out", "sale", "wanted_rent", "wanted_buy"],
    "transport-i-spectehnika": ["sale", "rent_out", "wanted_buy", "wanted_rent"],
    "reklama-i-marketing": ["service_offer", "service_wanted", "partnership"],
    "uslugi-dlya-biznesa": ["service_offer", "service_wanted", "tender", "partnership"],
    "logistika-i-perevozki": ["service_offer", "service_wanted", "tender"],
    "tovary-i-syryo-opt": ["sale", "wanted_buy", "partnership"],
    "gotovyy-biznes-i-franshizy": ["sale", "partnership", "wanted_buy"],
}

CATEGORY_ATTRIBUTES: dict[str, list[dict[str, Any]]] = {
    "oborudovanie": [
        {
            "key": "condition",
            "name": "Состояние",
            "type": "enum",
            "is_required": True,
            "options": [
                {"value": "new", "label": "Новое"},
                {"value": "used", "label": "Б/у"},
            ],
            "sort_order": 1,
        },
        {"key": "brand", "name": "Марка", "type": "string", "sort_order": 2},
        {"key": "year", "name": "Год выпуска", "type": "number", "sort_order": 3},
        {"key": "power_kw", "name": "Мощность", "type": "number", "unit": "кВт", "sort_order": 4},
        {"key": "warranty", "name": "Гарантия", "type": "bool", "sort_order": 5},
    ],
    "kommercheskaya-nedvizhimost": [
        {"key": "area", "name": "Площадь", "type": "number", "unit": "м²", "is_required": True, "sort_order": 1},
        {"key": "ceiling_height", "name": "Высота потолков", "type": "number", "unit": "м", "sort_order": 2},
        {"key": "utilities", "name": "Коммунальные подключены", "type": "bool", "sort_order": 3},
        {
            "key": "purpose",
            "name": "Назначение",
            "type": "enum",
            "options": [
                {"value": "office", "label": "Офис"},
                {"value": "retail", "label": "Торговля"},
                {"value": "warehouse", "label": "Склад"},
                {"value": "production", "label": "Производство"},
            ],
            "sort_order": 4,
        },
    ],
    "transport-i-spectehnika": [
        {"key": "brand", "name": "Марка", "type": "string", "sort_order": 1},
        {"key": "year", "name": "Год выпуска", "type": "number", "sort_order": 2},
        {"key": "mileage_km", "name": "Пробег", "type": "number", "unit": "км", "sort_order": 3},
        {"key": "capacity_t", "name": "Грузоподъёмность", "type": "number", "unit": "т", "sort_order": 4},
        {
            "key": "body_type",
            "name": "Тип кузова",
            "type": "enum",
            "options": [
                {"value": "tent", "label": "Тент"},
                {"value": "refrigerator", "label": "Реф"},
                {"value": "flatbed", "label": "Борт"},
                {"value": "tanker", "label": "Цистерна"},
            ],
            "sort_order": 5,
        },
    ],
    "reklama-i-marketing": [
        {
            "key": "service_format",
            "name": "Формат работы",
            "type": "enum",
            "options": [
                {"value": "online", "label": "Онлайн"},
                {"value": "offline", "label": "Офлайн"},
                {"value": "hybrid", "label": "Смешанный"},
            ],
            "sort_order": 1,
        },
        {"key": "deadline_days", "name": "Срок выполнения", "type": "number", "unit": "дней", "sort_order": 2},
    ],
    "uslugi-dlya-biznesa": [
        {
            "key": "service_format",
            "name": "Формат работы",
            "type": "enum",
            "options": [
                {"value": "remote", "label": "Удалённо"},
                {"value": "onsite", "label": "На месте"},
                {"value": "hybrid", "label": "Смешанный"},
            ],
            "sort_order": 1,
        },
        {"key": "experience_years", "name": "Опыт", "type": "number", "unit": "лет", "sort_order": 2},
    ],
    "logistika-i-perevozki": [
        {
            "key": "transport_type",
            "name": "Тип транспорта",
            "type": "enum",
            "options": [
                {"value": "truck", "label": "Грузовик"},
                {"value": "van", "label": "Фургон"},
                {"value": "refrigerator", "label": "Реф"},
                {"value": "special", "label": "Спецтехника"},
            ],
            "sort_order": 1,
        },
        {"key": "capacity_t", "name": "Грузоподъёмность", "type": "number", "unit": "т", "sort_order": 2},
        {"key": "route", "name": "Маршрут / зона", "type": "string", "sort_order": 3},
        {"key": "cargo_type", "name": "Тип груза", "type": "string", "sort_order": 4},
    ],
    "tovary-i-syryo-opt": [
        {"key": "volume", "name": "Объём партии", "type": "number", "sort_order": 1},
        {"key": "packaging", "name": "Упаковка", "type": "string", "sort_order": 2},
        {"key": "certification", "name": "Есть сертификаты", "type": "bool", "sort_order": 3},
    ],
    "gotovyy-biznes-i-franshizy": [
        {"key": "payback_months", "name": "Окупаемость", "type": "number", "unit": "мес.", "sort_order": 1},
        {"key": "revenue_month", "name": "Выручка в месяц", "type": "number", "unit": "₽", "sort_order": 2},
        {"key": "includes_assets", "name": "Включает активы", "type": "bool", "sort_order": 3},
    ],
}

PLANS: list[dict[str, Any]] = [
    {
        "code": "free",
        "name": "Бесплатный",
        "max_active_listings": 10,
        "price": 0,
        "features": {"promotion": False, "support": "community"},
        "description": "Стартовый тариф для проверки площадки.",
        "sort_order": 1,
    },
    {
        "code": "business",
        "name": "Бизнес",
        "max_active_listings": 50,
        "price": 2990,
        "features": {"promotion": True, "support": "email"},
        "description": "Для активных поставщиков и подрядчиков.",
        "sort_order": 2,
    },
    {
        "code": "pro",
        "name": "Профи",
        "max_active_listings": 200,
        "price": 7990,
        "features": {"promotion": True, "support": "priority"},
        "description": "Для компаний с большим каталогом.",
        "sort_order": 3,
    },
]

SETTINGS: list[dict[str, Any]] = [
    {
        "key": "limits.private_active_listings",
        "value": {"limit": 3},
        "description": "Лимит активных объявлений для частного лица",
    },
    {
        "key": "listings.default_ttl_days",
        "value": {"days": 30},
        "description": "Срок публикации объявления после одобрения",
    },
    {
        "key": "moderation.sla_hours",
        "value": {"hours": 24},
        "description": "SLA модерации",
    },
    {
        "key": "promotions.self_service",
        "value": {"enabled": False},
        "description": "Самостоятельное продвижение пользователями",
    },
    {
        "key": "contacts.visible_after_login",
        "value": {"enabled": True},
        "description": "Показывать контакты только авторизованным",
    },
]
