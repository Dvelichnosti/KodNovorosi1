# API Reference

Базовый URL: `https://<host>/api/v1`. Админ-API: `https://<host>/api/v1/admin`.

Машиночитаемая спецификация: [`openapi.json`](openapi.json). На запущенном
сервисе доступны `/docs`, `/redoc`, `/openapi.json`.

## 1. Общие правила

### 1.1. Заголовки

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

Для загрузки файлов используется `multipart/form-data`.

### 1.2. Аутентификация

| Обозначение | Значение |
|---|---|
| `—` | Публичный маршрут |
| `U` | Требуется `Authorization: Bearer <access_token>` |
| `U*` | Публичный, но с токеном доступны контакты и `is_favorite` |
| `O:<perm>` | Нужно участие в организации и организационное право |
| `A:<perm>` | Нужна платформенная роль, `mfa=true` и платформенное право |

Админ-запрос без `mfa=true` возвращает:

```json
{
  "error": {
    "code": "mfa_required",
    "message": "Требуется подтверждение TOTP"
  }
}
```

### 1.3. Формат ошибок

```json
{
  "error": {
    "code": "permission_denied",
    "message": "Недостаточно прав",
    "details": {"required": "org.manage_roles"}
  }
}
```

`details` необязателен. Ошибки валидации Pydantic имеют код
`validation_error` и массив деталей.

### 1.4. Пагинация

Запрос:

```http
GET /api/v1/listings?page=2&per_page=20
```

Ответ:

```json
{
  "items": [],
  "total": 0,
  "page": 2,
  "per_page": 20,
  "pages": 0
}
```

`page` начинается с 1, `per_page` — от 1 до 100. Если `per_page` не передан,
используется 20.

### 1.5. Время и идентификаторы

- Даты — ISO 8601 UTC.
- Идентификаторы — UUID.
- Телефоны нормализуются к виду `+79991234567`.
- Валюта по умолчанию — `RUB`.

### 1.6. Rate limit

При превышении возвращается `429`:

```json
{
  "error": {
    "code": "rate_limited",
    "message": "Слишком много запросов. Попробуйте позже.",
    "details": {"retry_after": 3600}
  }
}
```

Заголовок `Retry-After` содержит окно в секундах.

| Действие | По умолчанию |
|---|---|
| `POST /auth/telegram/start` | 10 запросов / 60 секунд на IP |
| `POST /auth/telegram/poll` | 60 запросов / 60 секунд на токен+IP |
| `POST /listings/{id}/complaints` | 5 жалоб / 3600 секунд на пользователя |
| `POST /uploads` | 30 загрузок / 3600 секунд на пользователя |

## 2. Аутентификация

### 2.1. Эндпоинты

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| POST | `/auth/telegram/start` | — | Создать сессию входа и deep-link |
| GET | `/auth/providers` | — | Список провайдеров входа |
| POST | `/auth/telegram/poll` | — | Проверить статус сессии входа |
| POST | `/auth/telegram/dev-confirm` | — | Подтвердить вход без бота (только dev) |
| POST | `/auth/refresh` | — | Обновить пару токенов |
| POST | `/auth/logout` | — | Отозвать refresh-токен |
| POST | `/auth/logout-all` | U | Отозвать все refresh-токены |
| GET | `/auth/me` | U | Текущий пользователь |
| GET | `/auth/totp/status` | U | Статус TOTP |
| POST | `/auth/totp/setup` | U + платформенная роль | Создать TOTP-секрет |
| POST | `/auth/totp/enable` | U + платформенная роль | Подтвердить и включить TOTP |
| POST | `/auth/totp/verify` | U + платформенная роль | Проверить код и получить `mfa=true` |

### 2.2. Начало входа

```http
POST /api/v1/auth/telegram/start
```

Ответ `200`:

```json
{
  "token": "Kj3...одноразовый...",
  "login_url": "https://t.me/BizBoardBot?start=login_Kj3...",
  "expires_in": 600
}
```

Клиент открывает `login_url`. Пользователь подтверждает вход в Telegram.
После этого клиент опрашивает статус.

### 2.3. Опрос статуса

```http
POST /api/v1/auth/telegram/poll
Content-Type: application/json

{"token": "Kj3...одноразовый..."}
```

Пока пользователь не подтвердил вход:

```json
{"status": "pending", "tokens": null}
```

После подтверждения:

```json
{
  "status": "confirmed",
  "tokens": {
    "access_token": "eyJ...",
    "refresh_token": "Yt7...",
    "token_type": "bearer",
    "expires_in": 900,
    "requires_totp": false,
    "totp_enabled": false,
    "user": {
      "id": "2f1c...",
      "full_name": "Иван Петров",
      "phone": "+79991234567",
      "phone_verified": true,
      "status": "active",
      "platform_roles": []
    }
  }
}
```

`requires_totp=true` означает, что пользователь имеет платформенную роль, но
токен выдан без MFA. Для доступа к админ-API нужно вызвать
`/auth/totp/verify` (или `/auth/totp/enable` при первой настройке).

### 2.4. Refresh и logout

```http
POST /api/v1/auth/refresh
Content-Type: application/json

{"refresh_token": "Yt7..."}
```

Ответ — новый `TokenPair`. Старый refresh-токен становится недействительным.
Повторное использование старого токена возвращает `401
refresh_reuse_detected` и отзывает всё семейство.

```http
POST /api/v1/auth/logout
Content-Type: application/json

{"refresh_token": "Yt7..."}
```

```http
POST /api/v1/auth/logout-all
Authorization: Bearer <access_token>
```

### 2.5. TOTP

```http
POST /api/v1/auth/totp/setup
Authorization: Bearer <access_token>
```

```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "otpauth_url": "otpauth://totp/BizBoard:...",
  "issuer": "BizBoard"
}
```

```http
POST /api/v1/auth/totp/enable
Authorization: Bearer <access_token>
Content-Type: application/json

{"code": "123456"}
```

Ответ — `TokenPair` с `mfa=true`. Для последующих входов:

```http
POST /api/v1/auth/totp/verify
Authorization: Bearer <access_token>
Content-Type: application/json

{"code": "123456"}
```

`GET /auth/totp/status`:

```json
{"enabled": true, "confirmed_at": "2026-11-13T10:00:00Z"}
```

## 3. Пользователи

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| GET | `/users/me` | U | Профиль |
| PATCH | `/users/me` | U | Обновить имя, email, уведомления |
| GET | `/users/me/favorites` | U | Избранные объявления |

`PATCH /users/me`:

```json
{
  "first_name": "Иван",
  "last_name": "Петров",
  "email": "ivan@example.com",
  "notification_settings": {
    "new_listing_moderated": true,
    "listing_expiring": false
  }
}
```

Допустимые ключи уведомлений: `new_listing_moderated`, `new_complaint`,
`new_invitation`, `listing_expiring`.

## 4. Организации

### 4.1. Эндпоинты

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| POST | `/organizations` | U | Создать организацию |
| GET | `/organizations/mine` | U | Мои организации |
| GET | `/organizations/{org_id}` | U + участник | Карточка организации |
| PATCH | `/organizations/{org_id}` | O | Обновить профиль/контакты |
| PUT | `/organizations/{org_id}/capabilities` | O | Заменить возможности |
| POST | `/organizations/{org_id}/verification/inn` | O | Проверить ИНН |
| POST | `/organizations/{org_id}/verification/documents` | U + участник | Загрузить документ |
| GET | `/organizations/{org_id}/verification/documents` | U + участник | Документы организации |
| GET | `/organizations/{org_id}/members` | U + участник | Сотрудники |
| PATCH | `/organizations/{org_id}/members/{user_id}` | `org.manage_members` | Сменить роль |
| DELETE | `/organizations/{org_id}/members/{user_id}` | `org.manage_members` | Удалить сотрудника |
| POST | `/organizations/{org_id}/invitations` | `org.manage_members` | Пригласить |
| GET | `/organizations/{org_id}/invitations` | `org.manage_members` | Список приглашений |
| DELETE | `/organizations/{org_id}/invitations/{invitation_id}` | `org.manage_members` | Отозвать приглашение |
| GET | `/organizations/{org_id}/roles` | U + участник | Роли |
| POST | `/organizations/{org_id}/roles` | `org.manage_roles` | Создать роль |
| PATCH | `/organizations/{org_id}/roles/{role_id}` | `org.manage_roles` | Обновить роль |
| DELETE | `/organizations/{org_id}/roles/{role_id}` | `org.manage_roles` | Удалить роль |
| POST | `/organizations/{org_id}/transfer-owner` | Владелец | Передать владение |
| POST | `/invitations/{token}/accept` | U | Принять приглашение |

### 4.2. Создание организации

```http
POST /api/v1/organizations
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "type": "legal_entity",
  "name": "ООО Ромашка",
  "inn": "7707083893",
  "region": "dnr",
  "address": "г. Донецк, ул. Артёма, 1",
  "phone": "+79991234567",
  "telegram": "@romashka",
  "description": "Поставка производственного оборудования",
  "capabilities": [
    {"code": "delivery", "params": {"zones": "ДНР, ЛНР", "same_day": true}}
  ]
}
```

Типы: `legal_entity`, `sole_proprietor`, `self_employed`.
Регионы: `dnr`, `lnr`, `kherson`, `zaporozhye`.

Правила:

- создатель становится владельцем;
- автоматически назначается бесплатный тариф;
- создаются три системные роли: «Менеджер объявлений», «Редактор профиля»,
  «Только просмотр»;
- ИНН проверяется по контрольной сумме; для юрлица — 10 цифр, для ИП и
  самозанятого — 12;
- если телефон совпадает с подтверждённым телефоном пользователя, организация
  получает уровень `phone`.

### 4.3. Обновление и права

`PATCH /organizations/{org_id}` принимает те же поля, что и создание, кроме
`capabilities`. Владелец может всё. Сотрудник:

- для профиля — `org.edit_profile`;
- для `phone`, `telegram`, `max_contact` — `org.manage_contacts`.

`PUT /organizations/{org_id}/capabilities`:

```json
{
  "capabilities": [
    {"code": "transport", "params": {"body_types": ["tent", "refrigerator"]}},
    {"code": "vat", "params": {}}
  ]
}
```

Коды возможностей: `transport`, `delivery`, `installation`, `rent`, `vat`,
`government_order`.

### 4.4. Верификация

```http
POST /api/v1/organizations/{org_id}/verification/inn
Content-Type: application/json

{"inn": "7707083893"}
```

Уровни: `none` → `phone` → `inn` → `moderator`.

Документы:

```http
POST /api/v1/organizations/{org_id}/verification/documents
Content-Type: multipart/form-data

kind=egrul
file=@egrul.pdf
```

Типы документов: `egrul`, `egrip`, `self_employed`, `other`.
Форматы: PDF, JPEG, PNG. Документ получает статус `pending` и проверяется
администратором.

### 4.5. Участники и роли

Приглашение:

```http
POST /api/v1/organizations/{org_id}/invitations
Content-Type: application/json

{
  "role_id": "6a5d...",
  "telegram_id": 123456789
}
```

Ответ `201`:

```json
{
  "id": "e1d2...",
  "token": "Xk9...",
  "invite_url": "https://t.me/BizBoardBot?start=invite_Xk9...",
  "expires_at": "2026-11-16T10:00:00Z"
}
```

Срок жизни приглашения — `INVITATION_TTL_HOURS` (по умолчанию 72 часа).
Если указан `telegram_id`, принять приглашение может только этот аккаунт.
При входе через Telegram приглашения принимаются автоматически.

Смена роли:

```http
PATCH /api/v1/organizations/{org_id}/members/{user_id}
Content-Type: application/json

{"role_id": "6a5d..."}
```

`role_id: null` снимает роль, оставляя сотрудника без прав.

Создание роли:

```http
POST /api/v1/organizations/{org_id}/roles
Content-Type: application/json

{
  "name": "Менеджер продаж",
  "permissions": ["listing.create", "listing.edit", "listing.publish"]
}
```

Ограничения:

- имя роли уникально внутри организации;
- неизвестный код права → `422 unknown_permission`;
- нельзя выдать право, которого нет у выдающего → `403 permission_escalation`;
- роль, назначенную сотрудникам, нельзя удалить → `409 role_in_use`;
- роль владельца нельзя изменить через участников → `409 owner_role_immutable`.

Передача владения:

```http
POST /api/v1/organizations/{org_id}/transfer-owner
Content-Type: application/json

{"user_id": "b3c4..."}
```

## 5. Каталог, справочники и тарифы

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| GET | `/catalog/categories` | — | Дерево активных категорий |
| GET | `/catalog/categories/{category_id}` | — | Категория с атрибутами и предками |
| GET | `/catalog/capabilities` | — | Справочник возможностей |
| GET | `/meta` | — | Все справочники и коды прав |
| GET | `/plans` | — | Активные тарифы |

`GET /catalog/categories` возвращает массив корневых категорий с вложенными
`children`. Атрибуты категории включают унаследованные от предков.

`GET /meta` возвращает:

```json
{
  "regions": {"dnr": "ДНР", "...": "..."},
  "org_types": {"legal_entity": "Юридическое лицо", "...": "..."},
  "verification_levels": {"none": "Без верификации", "...": "..."},
  "listing_types": {"sale": "Продам", "...": "..."},
  "listing_statuses": {"draft": "Черновик", "...": "..."},
  "complaint_reasons": {"spam": "Спам или дубль", "...": "..."},
  "complaint_statuses": {"new": "Новая", "...": "..."},
  "attribute_types": {"string": "Строка", "...": "..."},
  "org_permissions": {"listing.create": "Создавать объявления", "...": "..."},
  "platform_permissions": {"users.view": "Просмотр пользователей", "...": "..."}
}
```

## 6. Объявления

### 6.1. Эндпоинты

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| GET | `/listings` | U* | Поиск активных объявлений |
| GET | `/listings/mine` | U | Мои объявления и объявления моих организаций |
| GET | `/listings/{listing_id}` | U* | Карточка объявления |
| POST | `/listings` | U | Создать черновик |
| PATCH | `/listings/{listing_id}` | Автор или `listing.edit` | Изменить |
| DELETE | `/listings/{listing_id}` | Автор или `listing.delete` | Мягко удалить |
| POST | `/listings/{listing_id}/submit` | Автор или `listing.publish` | Отправить на модерацию |
| POST | `/listings/{listing_id}/archive` | Автор или `listing.edit` | В архив |
| GET | `/listings/{listing_id}/stats` | Автор или `listing.view_stats` | Статистика |
| POST | `/listings/{listing_id}/favorite` | U | В избранное |
| DELETE | `/listings/{listing_id}/favorite` | U | Из избранного |
| POST | `/listings/{listing_id}/complaints` | U | Пожаловаться |
| POST | `/listings/{listing_id}/bump` | Автор или `listing.promote` | Поднять (если включено) |

### 6.2. Поиск

```http
GET /api/v1/listings?q=токарный&region=dnr&category_id=<uuid>&sort=relevance
```

Параметры:

| Параметр | Описание |
|---|---|
| `q` | Полнотекстовый запрос по заголовку и описанию |
| `category_id` | Категория и все её потомки |
| `type` | Один из 8 типов объявления |
| `region` | Регион |
| `price_min`, `price_max` | Диапазон цены |
| `organization_id` | Объявления организации |
| `sort` | `date`, `price_asc`, `price_desc`, `relevance` |
| `page`, `per_page` | Пагинация |
| `attr.<key>` | Точное значение атрибута |
| `attr.<key>.min` | Минимум для числового атрибута |
| `attr.<key>.max` | Максимум для числового атрибута |

Пример:

```http
GET /api/v1/listings?attr.condition=used&attr.year.min=2019&attr.year.max=2021
```

Правила выдачи:

- только `active`, не удалённые и не истёкшие;
- `contacts` отсутствуют без авторизации, `contacts_available=false`;
- с авторизацией контакты доступны, `is_favorite` отражает избранное;
- `top`-продвижения поднимаются выше в сортировке по дате.

### 6.3. Создание

```http
POST /api/v1/listings
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Станок токарный в отличном состоянии",
  "description": "Продаём производственный токарный станок, 2020 год выпуска.",
  "category_id": "8f2a...",
  "type": "sale",
  "region": "dnr",
  "city": "Донецк",
  "address": "ул. Артёма, 1",
  "price": 250000,
  "currency": "RUB",
  "price_unit": "за единицу",
  "negotiable": true,
  "attributes": {"condition": "used", "year": 2020},
  "organization_id": "b3c4...",
  "contact_phone": "+79991234567",
  "contact_telegram": "@ivan",
  "contact_max": "@ivan"
}
```

Ограничения:

- `title` — 5–255 символов;
- `description` — 10–20 000 символов;
- `price >= 0`;
- категория должна быть активной;
- тип должен быть разрешён для категории (`allowed_types`);
- обязательные атрибуты категории должны быть заполнены;
- при публикации от организации нужно право `listing.create`.

Создаётся со статусом `draft`. Контакты по умолчанию берутся из организации
или профиля пользователя.

### 6.4. Жизненный цикл

```text
draft ──submit──▶ pending ──approve──▶ active ──expire──▶ expired
  ▲                  │                    │
  │                  └──reject──▶ rejected│
  │                                      ├──archive──▶ archived
  └──────────edit rejected───────────────┘
                     active ──edit──▶ pending
                     active ──block──▶ blocked
```

- `submit` разрешён только из `draft` или `rejected`.
- Перед отправкой повторно проверяются атрибуты и лимит публикаций.
- При одобрении выставляются `published_at`, `bumped_at` и `expires_at`
  (`DEFAULT_LISTING_TTL_DAYS`, по умолчанию 30 дней).
- Редактирование активного объявления возвращает его в `pending`.
- Редактирование отклонённого возвращает в `draft`.
- `blocked` и `archived` нельзя редактировать.
- Удаление — мягкое (`deleted_at`), статус становится `archived`.

Лимиты:

- частное лицо — `PRIVATE_ACTIVE_LISTING_LIMIT` (по умолчанию 3);
- организация — `plans.max_active_listings` активного тарифа;
- учитываются статусы `active` и `pending`;
- при превышении — `403 listing_limit_reached`.

### 6.5. Статистика

```json
{
  "listing_id": "a1b2...",
  "total_views": 128,
  "views_7d": 41,
  "views_30d": 120,
  "favorites_count": 7,
  "status": "active",
  "published_at": "2026-11-01T10:00:00Z",
  "expires_at": "2026-12-01T10:00:00Z"
}
```

### 6.6. Жалобы

```http
POST /api/v1/listings/{listing_id}/complaints
Content-Type: application/json

{"reason": "fraud", "comment": "Просят предоплату без договора"}
```

Причины: `spam`, `fraud`, `wrong_category`, `prohibited`, `offensive`, `other`.

Нельзя жаловаться на своё объявление (`409 own_listing_complaint`) или на
объявление своей организации (`409 own_org_complaint`).

### 6.7. Продвижение

Самостоятельное продвижение по умолчанию выключено
(`PROMOTIONS_SELF_SERVICE=false`). В этом случае `POST /bump` возвращает
`403 promotions_disabled`. Продвижение назначает администратор:

- `top` — приоритет в выдаче;
- `highlight` — визуальное выделение;
- `bump` — поднятие по `bumped_at`;
- по умолчанию срок — 7 дней.

## 7. Загрузка файлов

```http
POST /api/v1/uploads
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

kind=image
file=@photo.jpg
```

`kind`: `image`, `logo`, `document`.

| Тип | Форматы | Публичный |
|---|---|---|
| `image` | JPEG, PNG, WebP | да |
| `logo` | JPEG, PNG, WebP | да |
| `document` | PDF, JPEG, PNG | нет |

Максимальный размер — `MAX_UPLOAD_MB` (20 МБ). Ответ `201`:

```json
{
  "id": "f1e2...",
  "kind": "image",
  "filename": "9a8b....jpg",
  "original_name": "photo.jpg",
  "content_type": "image/jpeg",
  "size": 245678,
  "url": "/media/image/<user_id>/9a8b....jpg",
  "is_public": true,
  "created_at": "2026-11-13T10:00:00Z"
}
```

Файлы отдаются статикой по `MEDIA_URL` (`/media`).

## 8. Публичные организации

| Метод | Путь | Доступ | Описание |
|---|---|---|---|
| GET | `/public/organizations` | — | Поиск активных организаций |
| GET | `/public/organizations/{slug}` | — | Публичная карточка |

Параметры поиска: `q`, `region`, `type`, `capability`, `verification_level`,
`page`, `per_page`.

В публичной карточке нет ИНН, документов и служебных полей; контакты
организации доступны, так как это её витрина.

## 9. Telegram webhook

```http
POST /api/v1/telegram/webhook
X-Telegram-Bot-Api-Secret-Token: <secret>
```

Обрабатывает:

- `/start login_<token>` — подтверждение входа;
- `/start invite_<token>` — принятие приглашения;
- контакт от пользователя — подтверждение телефона.

Если `TELEGRAM_WEBHOOK_SECRET` задан, запрос без корректного заголовка
отклоняется с `403 invalid_webhook_secret`. Ошибки обработки логируются, но
Telegram всё равно получает `200`, чтобы избежать повторной доставки.

## 10. Админ-API

Все маршруты требуют `Authorization: Bearer <access_token>` с `mfa=true` и
указанное платформенное право.

### 10.1. Сводка

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/stats` | любое из `users.view`, `orgs.verify`, `listings.moderate`, `complaints.handle` | Счётчики |

Ответ:

```json
{
  "users_total": 1200,
  "users_blocked": 3,
  "organizations_total": 140,
  "organizations_pending_verification": 7,
  "listings_total": 5300,
  "listings_pending": 12,
  "listings_active": 4100,
  "complaints_new": 4,
  "documents_pending": 2
}
```

### 10.2. Пользователи

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/users` | `users.view` | Список, фильтры `q`, `status`, `role` |
| GET | `/admin/users/{user_id}` | `users.view` | Карточка |
| POST | `/admin/users/{user_id}/block` | `users.block` | Блокировка |
| POST | `/admin/users/{user_id}/unblock` | `users.block` | Разблокировка |
| POST | `/admin/users/{user_id}/platform-roles` | `roles.manage_platform` | Выдать роль |
| DELETE | `/admin/users/{user_id}/platform-roles/{role_id}` | `roles.manage_platform` | Снять роль |

Блокировка:

```json
{"reason": "Спам в объявлениях"}
```

Правила: нельзя заблокировать себя (`cannot_block_self`), нельзя заблокировать
суперадмина без роли суперадмина (`cannot_block_superadmin`), нельзя снять
последнюю роль суперадмина (`last_superadmin`).

### 10.3. Платформенные роли

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/platform-roles` | `roles.manage_platform` | Список |
| POST | `/admin/platform-roles` | `roles.manage_platform` | Создать |
| PATCH | `/admin/platform-roles/{role_id}` | `roles.manage_platform` | Обновить |
| DELETE | `/admin/platform-roles/{role_id}` | `roles.manage_platform` | Удалить |

```json
{
  "code": "moderator_listings",
  "name": "Модератор объявлений",
  "permissions": ["listings.moderate", "complaints.handle"]
}
```

Системную роль удалить нельзя (`system_role_immutable`), назначенную —
нельзя (`role_in_use`).

### 10.4. Организации и верификация

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/organizations` | `orgs.verify` | Список, фильтры `q`, `status`, `verification_level` |
| GET | `/admin/organizations/{org_id}` | `orgs.verify` | Карточка |
| POST | `/admin/organizations/{org_id}/verify` | `orgs.verify` | Решение по верификации |
| GET | `/admin/organizations/{org_id}/documents` | `orgs.verify` | Документы |
| POST | `/admin/organizations/{org_id}/documents/{document_id}/review` | `orgs.verify` | Проверить документ |
| POST | `/admin/organizations/{org_id}/plan` | `plans.manage` | Назначить тариф |

Верификация организации:

```json
{"decision": "approve", "comment": null}
```

или:

```json
{"decision": "reject", "comment": "Документы нечитаемы"}
```

При отказе комментарий обязателен (`rejection_reason_required`).
Одобрение поднимает уровень до `moderator`.

Проверка документа:

```json
{"decision": "approve", "comment": "ОК"}
```

Назначение тарифа:

```json
{"plan_id": "d4e5...", "expires_at": "2027-01-01T00:00:00Z"}
```

`plan_id: null` снимает тариф.

### 10.5. Модерация объявлений

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/listings` | `listings.moderate` | Очередь, фильтры `q`, `status` |
| GET | `/admin/listings/{listing_id}` | `listings.moderate` | Карточка |
| POST | `/admin/listings/{listing_id}/approve` | `listings.moderate` | Одобрить |
| POST | `/admin/listings/{listing_id}/reject` | `listings.moderate` | Отклонить |
| POST | `/admin/listings/{listing_id}/block` | `listings.moderate` | Заблокировать |
| POST | `/admin/listings/{listing_id}/promote` | `listings.moderate` | Назначить продвижение |
| DELETE | `/admin/listings/{listing_id}/promotions/{promotion_id}` | `listings.moderate` | Снять продвижение |

Отклонение и блокировка требуют причину:

```json
{"reason": "Неверная категория"}
```

Продвижение:

```json
{
  "type": "top",
  "starts_at": "2026-11-13T00:00:00Z",
  "ends_at": "2026-11-20T00:00:00Z"
}
```

Продвигать можно только `active` объявление (`listing_not_active`).

### 10.6. Жалобы

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/complaints` | `complaints.handle` | Список, фильтр `status` |
| POST | `/admin/complaints/{complaint_id}/take` | `complaints.handle` | Взять в работу |
| POST | `/admin/complaints/{complaint_id}/resolve` | `complaints.handle` | Решить |

```json
{"status": "resolved", "resolution": "Нарушений не выявлено"}
```

Допустимые финальные статусы: `resolved`, `rejected`.

### 10.7. Каталог

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/catalog/categories` | `catalog.manage` | Дерево, включая неактивные |
| GET | `/admin/catalog/categories/{category_id}` | `catalog.manage` | Детали |
| POST | `/admin/catalog/categories` | `catalog.manage` | Создать |
| PATCH | `/admin/catalog/categories/{category_id}` | `catalog.manage` | Обновить |
| DELETE | `/admin/catalog/categories/{category_id}` | `catalog.manage` | Удалить |
| POST | `/admin/catalog/categories/{category_id}/attributes` | `catalog.manage` | Создать атрибут |
| PATCH | `/admin/catalog/attributes/{attribute_id}` | `catalog.manage` | Обновить атрибут |
| DELETE | `/admin/catalog/attributes/{attribute_id}` | `catalog.manage` | Удалить атрибут |

Создание категории:

```json
{
  "name": "Пищевое оборудование",
  "parent_id": "8f2a...",
  "description": "Печи, тестомесы, витрины",
  "sort_order": 10,
  "is_active": true,
  "allowed_types": ["sale", "rent_out"]
}
```

Ограничения:

- глубина не более 3 уровней (`category_depth_exceeded`);
- нельзя создать цикл (`category_cycle`);
- нельзя удалить категорию с детьми (`category_has_children`) или объявлениями
  (`category_has_listings`);
- slug генерируется автоматически, при необходимости добавляется суффикс.

Создание атрибута:

```json
{
  "key": "power_kw",
  "name": "Мощность",
  "type": "number",
  "unit": "кВт",
  "is_required": false,
  "is_filterable": true,
  "options": [],
  "sort_order": 4
}
```

Для `enum` и `multi_enum` обязателен непустой `options`.

### 10.8. Тарифы

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/plans` | `plans.manage` | Все тарифы |
| POST | `/admin/plans` | `plans.manage` | Создать |
| PATCH | `/admin/plans/{plan_id}` | `plans.manage` | Обновить |
| DELETE | `/admin/plans/{plan_id}` | `plans.manage` | Удалить |

```json
{
  "code": "business",
  "name": "Бизнес",
  "max_active_listings": 50,
  "price": 2990,
  "currency": "RUB",
  "features": {"promotion": true, "support": "email"},
  "description": "Для активных поставщиков",
  "is_active": true,
  "sort_order": 2
}
```

Нельзя удалить тариф, назначенный организациям (`plan_in_use`).

### 10.9. Аудит и настройки

| Метод | Путь | Право | Описание |
|---|---|---|---|
| GET | `/admin/audit` | `audit.view` | Журнал, фильтры `actor_id`, `action`, `entity_type` |
| GET | `/admin/settings` | `settings.manage` | Настройки |
| PUT | `/admin/settings/{key}` | `settings.manage` | Создать/обновить |

```http
PUT /api/v1/admin/settings/moderation.sla_hours
Content-Type: application/json

{"value": {"hours": 12}, "description": "SLA модерации"}
```

Аудит фиксирует действия администраторов: блокировки, верификацию, модерацию,
жалобы, изменения каталога, тарифов, ролей и настроек.

## 11. Коды ошибок

### 11.1. Аутентификация и доступ

| Код | HTTP | Значение |
|---|---|---|
| `unauthorized` | 401 | Нет или не передан токен |
| `invalid_token` | 401 | Токен не декодируется |
| `invalid_token_type` | 401 | Передан refresh вместо access |
| `token_expired` | 401 | Access-токен истёк |
| `invalid_refresh_token` | 401 | Refresh-токен не найден |
| `refresh_expired` | 401 | Refresh-токен истёк |
| `refresh_reuse_detected` | 401 | Повторное использование, семейство отозвано |
| `account_blocked` | 403 | Пользователь заблокирован |
| `mfa_required` | 403 | Нужен TOTP |
| `not_platform_user` | 403 | TOTP только для платформенных ролей |
| `permission_denied` | 403 | Нет нужного права |
| `not_org_member` | 403 | Нет участия в организации |
| `permission_escalation` | 403 | Попытка выдать больше прав, чем есть |
| `owner_required` | 403 | Действие только для владельца |

### 11.2. Вход и TOTP

| Код | HTTP | Значение |
|---|---|---|
| `login_not_found` | 404 | Сессия входа не найдена |
| `login_expired` | 410 | Сессия входа истекла |
| `login_used` | 410 | Сессия уже использована |
| `login_incomplete` | 409 | Сессия без пользователя |
| `totp_not_setup` | 400 | TOTP не настроен |
| `totp_not_enabled` | 400 | TOTP не включён |
| `totp_already_enabled` | 409 | TOTP уже включён |
| `invalid_totp_code` | 400 | Неверный код |
| `totp_decrypt_error` | 500 | Не удалось расшифровать секрет |

### 11.3. Организации и приглашения

| Код | HTTP | Значение |
|---|---|---|
| `organization_not_found` | 404 | Организация не найдена |
| `member_not_found` | 404 | Сотрудник не найден |
| `role_not_found` | 404 | Роль не найдена |
| `role_exists` | 409 | Имя роли занято |
| `role_in_use` | 409 | Роль назначена сотрудникам |
| `role_required` | 422 | Не указана роль при приглашении |
| `role_not_assigned` | 404 | Роль не назначена пользователю |
| `owner_role_immutable` | 409 | Нельзя менять роль владельца |
| `owner_cannot_be_removed` | 409 | Нельзя удалить владельца |
| `invitation_not_found` | 404 | Приглашение не найдено |
| `invitation_not_pending` | 410 | Приглашение использовано или отозвано |
| `invitation_expired` | 410 | Приглашение истекло |
| `invitation_owner_mismatch` | 403 | Приглашение другому Telegram-аккаунту |
| `unknown_capability` | 422 | Неизвестная возможность |
| `duplicate_capability` | 422 | Дубликат возможности |
| `invalid_inn` | 422 | ИНН не прошёл проверку |
| `inn_taken` | 409 | ИНН уже используется |
| `document_not_found` | 404 | Документ не найден |
| `rejection_reason_required` | 422 | Нужна причина отказа |

### 11.4. Каталог и объявления

| Код | HTTP | Значение |
|---|---|---|
| `category_not_found` | 404 | Категория не найдена |
| `category_depth_exceeded` | 422 | Больше 3 уровней |
| `category_cycle` | 422 | Цикл в дереве |
| `category_has_children` | 409 | Есть дочерние категории |
| `category_has_listings` | 409 | Есть объявления |
| `category_inactive` | 422 | Категория отключена |
| `attribute_not_found` | 404 | Атрибут не найден |
| `attribute_exists` | 409 | Ключ атрибута занят |
| `attribute_options_required` | 422 | Нужны варианты |
| `invalid_attribute_type` | 422 | Неизвестный тип атрибута |
| `invalid_attributes` | 422 | Ошибка значений атрибутов |
| `invalid_listing_types` | 422 | Недопустимые типы категории |
| `listing_type_not_allowed` | 422 | Тип не разрешён категории |
| `listing_not_found` | 404 | Объявление не найдено |
| `listing_not_editable` | 409 | Статус не допускает редактирование |
| `invalid_listing_status` | 409 | Недопустимый переход статуса |
| `listing_limit_reached` | 403 | Достигнут лимит публикаций |
| `listing_not_active` | 409 | Продвижение только для активных |
| `invalid_promotion` | 422 | Неизвестный тип продвижения |
| `promotion_not_found` | 404 | Продвижение не найдено |
| `promotions_disabled` | 403 | Самостоятельное продвижение выключено |
| `invalid_decision` | 422 | Неизвестное решение модератора |
| `block_reason_required` | 422 | Нужна причина блокировки |

### 11.5. Жалобы, файлы, общее

| Код | HTTP | Значение |
|---|---|---|
| `complaint_not_found` | 404 | Жалоба не найдена |
| `invalid_complaint_reason` | 422 | Недопустимая причина |
| `own_listing_complaint` | 409 | Жалоба на своё объявление |
| `own_org_complaint` | 409 | Жалоба на объявление своей организации |
| `invalid_upload_kind` | 422 | Неизвестный тип загрузки |
| `invalid_file_type` | 422 | Недопустимый MIME-тип |
| `file_too_large` | 413 | Файл больше лимита |
| `empty_file` | 422 | Пустой файл |
| `invalid_phone` | 422 | Некорректный телефон |
| `invalid_json` | 400 | Некорректный JSON вебхука |
| `invalid_webhook_secret` | 403 | Неверный секрет вебхука |
| `rate_limited` | 429 | Превышен лимит запросов |
| `validation_error` | 422 | Ошибка схемы запроса |
| `internal_error` | 500 | Внутренняя ошибка |

## 12. Пример полного сценария

```bash
# 1. Начать вход
curl -X POST https://api.example.com/api/v1/auth/telegram/start

# 2. Пользователь открыл login_url и подтвердил вход в Telegram
curl -X POST https://api.example.com/api/v1/auth/telegram/poll \
  -H "Content-Type: application/json" \
  -d '{"token":"<token>"}'

# 3. Создать организацию
curl -X POST https://api.example.com/api/v1/organizations \
  -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"type":"legal_entity","name":"ООО Ромашка","region":"dnr","phone":"+79991234567"}'

# 4. Создать черновик
curl -X POST https://api.example.com/api/v1/listings \
  -H "Authorization: Bearer <access>" \
  -H "Content-Type: application/json" \
  -d '{"title":"Станок токарный","description":"Продаём станок 2020 года.","category_id":"<uuid>","type":"sale","region":"dnr","attributes":{"condition":"used"},"organization_id":"<uuid>"}'

# 5. Отправить на модерацию
curl -X POST https://api.example.com/api/v1/listings/<listing_id>/submit \
  -H "Authorization: Bearer <access>"

# 6. Публичный поиск (контакты скрыты)
curl "https://api.example.com/api/v1/listings?q=токарный&region=dnr"
```
