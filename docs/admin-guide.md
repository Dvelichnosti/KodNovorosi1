# Руководство администратора

Документ для сотрудников платформы: модераторов, верификаторов, поддержки и
суперадминов. Описывает ежедневные действия через админ-API.

## 1. Доступ

### 1.1. Роли и права

| Роль при seed | Права |
|---|---|
| `superadmin` | Все платформенные права |
| `moderator` | `users.view`, `orgs.verify`, `listings.moderate`, `complaints.handle`, `catalog.manage`, `audit.view` |
| `support` | `users.view`, `orgs.verify`, `complaints.handle` |

Полный список прав:

| Код | Что разрешает |
|---|---|
| `users.view` | Смотреть пользователей |
| `users.block` | Блокировать и разблокировать |
| `orgs.verify` | Проверять организации и документы |
| `listings.moderate` | Модерировать и продвигать объявления |
| `complaints.handle` | Обрабатывать жалобы |
| `catalog.manage` | Управлять каталогом и атрибутами |
| `roles.manage_platform` | Управлять платформенными ролями |
| `plans.manage` | Управлять тарифами |
| `audit.view` | Читать журнал аудита |
| `settings.manage` | Менять настройки платформы |

Роли можно комбинировать: права пользователя — объединение прав всех его
платформенных ролей.

### 1.2. Первый вход и TOTP

Админ-API требует **и `mfa=true` в access-токене, и конкретное право**.

```text
1. Войти через Telegram            → токен с mfa=false
2. POST /auth/totp/setup           → секрет + otpauth-ссылка
3. Добавить секрет в authenticator → Google Authenticator, Authy, 1Password
4. POST /auth/totp/enable {code}   → токены с mfa=true
5. При следующих входах:
   POST /auth/totp/verify {code}   → токены с mfa=true
```

Если TOTP ещё не настроен, `setup` и `enable` доступны по обычному токену.
`mfa_required` означает, что токен не прошёл TOTP. `totp_not_enabled` —
секрет есть, но не подтверждён.

### 1.3. Заголовки

```http
Authorization: Bearer <access_token с mfa=true>
Content-Type: application/json
```

Access-токен живёт 15 минут. При `401 token_expired` обновите пару через
`POST /auth/refresh`, затем повторите запрос.

## 2. Сводка

```http
GET /api/v1/admin/stats
```

Доступна любому из прав: `users.view`, `orgs.verify`, `listings.moderate`,
`complaints.handle`.

| Поле | Что значит |
|---|---|
| `users_total` | Всего пользователей |
| `users_blocked` | Заблокированные |
| `organizations_total` | Активные организации |
| `organizations_pending_verification` | Активные без уровня `moderator` |
| `listings_total` | Не удалённые объявления |
| `listings_pending` | Очередь модерации |
| `listings_active` | Опубликованные |
| `complaints_new` | Новые жалобы |
| `documents_pending` | Документы на проверке |

Используйте сводку как утренний чек-лист: сначала `documents_pending` и
`complaints_new`, затем `listings_pending`.

## 3. Модерация объявлений

### 3.1. Очередь

```http
GET /api/v1/admin/listings?status=pending&page=1&per_page=20
```

Фильтры: `q` (поиск по заголовку/описанию), `status`. Сортировка — сначала
старые, чтобы не нарушать SLA.

Статусы:

| Статус | Значение |
|---|---|
| `draft` | Черновик, не отправлен |
| `pending` | Ждёт модерации |
| `active` | Опубликован |
| `rejected` | Отклонён, автор может исправить |
| `archived` | В архиве |
| `expired` | Истёк срок |
| `blocked` | Заблокирован модератором |

### 3.2. Что проверить

1. **Заголовок и описание** — соответствуют товару/услуге, без спама,
   CAPS LOCK, контактов в тексте (контакты должны быть в полях).
2. **Категория** — правильная, без обхода (например, «услуги» вместо
   «оборудование»).
3. **Тип** — `sale`, `rent_out`, `wanted_buy`, `wanted_rent`,
   `service_offer`, `service_wanted`, `tender`, `partnership`.
4. **Регион и город** — в пределах ДНР, ЛНР, Херсонской или Запорожской
   области.
5. **Цена** — не отрицательная, валюта корректна, нет «1 руб.» как приманки.
6. **Атрибуты** — заполнены обязательные, значения осмысленны.
7. **Контакты** — телефон/Telegram/MAX, не чужие данные.
8. **Изображения** — если приложены, соответствуют описанию.
9. **Признаки мошенничества** — предоплата, «только по 100% оплате»,
   подозрительные ссылки.

### 3.3. Решения

```http
POST /api/v1/admin/listings/{id}/approve
```

Одобрение:

- статус → `active`;
- `published_at`, `bumped_at` = сейчас;
- `expires_at` = сейчас + `DEFAULT_LISTING_TTL_DAYS` (30 дней).

```http
POST /api/v1/admin/listings/{id}/reject
{"reason": "Неверная категория"}
```

Отклонение:

- статус → `rejected`;
- причина обязательна (`block_reason_required`);
- автор увидит причину и сможет исправить и отправить снова.

```http
POST /api/v1/admin/listings/{id}/block
{"reason": "Мошенническая схема"}
```

Блокировка:

- статус → `blocked`;
- причина обязательна;
- используется для нарушений, а не для обычных правок;
- объявление исчезает из публичной выдачи.

### 3.4. Продвижение

```http
POST /api/v1/admin/listings/{id}/promote
{
  "type": "top",
  "starts_at": "2026-11-13T00:00:00Z",
  "ends_at": "2026-11-20T00:00:00Z"
}
```

| Тип | Эффект |
|---|---|
| `top` | Приоритет в выдаче |
| `highlight` | Визуальное выделение |
| `bump` | Поднятие по `bumped_at` |

Ограничения:

- продвигать можно только `active`;
- по умолчанию срок — 7 дней;
- самостоятельное продвижение пользователями выключено
  (`PROMOTIONS_SELF_SERVICE=false`), назначает администратор;
- снять: `DELETE /api/v1/admin/listings/{id}/promotions/{promotion_id}`.

## 4. Жалобы

### 4.1. Очередь

```http
GET /api/v1/admin/complaints?status=new
```

Причины жалоб: `spam`, `fraud`, `wrong_category`, `prohibited`, `offensive`,
`other`.

### 4.2. Взять в работу

```http
POST /api/v1/admin/complaints/{id}/take
```

Статус → `in_review`, фиксируется `handled_by`. Это сигнал другим
модераторам, что жалоба уже разбирается.

### 4.3. Решить

```http
POST /api/v1/admin/complaints/{id}/resolve
{"status": "resolved", "resolution": "Нарушений не выявлено"}
```

Допустимые финальные статусы: `resolved`, `rejected`.

Рекомендации:

- `resolved` — жалоба подтвердилась, приняты меры (блокировка, отклонение);
- `rejected` — нарушения нет;
- в `resolution` пишите факт и действие, без персональных данных.

Если жалоба подтвердилась, отдельно примените решение к объявлению
(`reject`/`block`) — `resolve` сам статус объявления не меняет.

## 5. Верификация организаций

### 5.1. Очередь

```http
GET /api/v1/admin/organizations?verification_level=phone
```

Уровни: `none` → `phone` → `inn` → `moderator`.

- `none` — без подтверждений;
- `phone` — телефон совпал с подтверждённым телефоном пользователя;
- `inn` — ИНН прошёл проверку контрольной суммы;
- `moderator` — документы проверены вручную.

### 5.2. Документы

```http
GET /api/v1/admin/organizations/{org_id}/documents
```

Типы: `egrul`, `egrip`, `self_employed`, `other`.
Статусы: `pending`, `approved`, `rejected`.

Проверка:

```http
POST /api/v1/admin/organizations/{org_id}/documents/{document_id}/review
{"decision": "approve", "comment": "Выписка актуальна"}
```

При отказе комментарий обязателен. Проверяйте:

- читаемость и актуальность;
- совпадение названия, ИНН и ОГРН с карточкой;
- соответствие типа организации (юрлицо → ЕГРЮЛ, ИП → ЕГРИП,
  самозанятый → справка);
- отсутствие признаков редактирования.

### 5.3. Решение по организации

```http
POST /api/v1/admin/organizations/{org_id}/verify
{"decision": "approve", "comment": null}
```

```json
{"decision": "reject", "comment": "Документы нечитаемы"}
```

- `approve` поднимает уровень до `moderator`;
- `reject` требует комментарий (`rejection_reason_required`);
- решение пишется в аудит.

## 6. Тарифы и лимиты

### 6.1. Назначение тарифа

```http
POST /api/v1/admin/organizations/{org_id}/plan
{"plan_id": "d4e5...", "expires_at": "2027-01-01T00:00:00Z"}
```

`plan_id: null` снимает тариф. Требуется право `plans.manage`.

Тарифы при seed:

| Код | Лимит активных объявлений | Цена |
|---|---|---|
| `free` | 10 | 0 |
| `business` | 50 | 2990 |
| `pro` | 200 | 7990 |

Лимит частного лица — `PRIVATE_ACTIVE_LISTING_LIMIT` (3). Он ниже лимитов
организаций.

### 6.2. Управление тарифами

```http
GET    /api/v1/admin/plans
POST   /api/v1/admin/plans
PATCH  /api/v1/admin/plans/{plan_id}
DELETE /api/v1/admin/plans/{plan_id}
```

Тариф, назначенный организациям, удалить нельзя (`plan_in_use`).

## 7. Пользователи

### 7.1. Поиск

```http
GET /api/v1/admin/users?q=+7999&status=active&role=moderator
```

Карточка: `GET /api/v1/admin/users/{user_id}`.

### 7.2. Блокировка

```http
POST /api/v1/admin/users/{user_id}/block
{"reason": "Спам в объявлениях"}
```

```http
POST /api/v1/admin/users/{user_id}/unblock
```

Правила:

- нельзя заблокировать себя (`cannot_block_self`);
- нельзя заблокировать суперадмина (`cannot_block_superadmin`);
- блокировка отзывает refresh-токены и запрещает доступ;
- причина фиксируется в аудите.

### 7.3. Платформенные роли

```http
POST /api/v1/admin/users/{user_id}/platform-roles
{"role_id": "a1b2..."}
```

```http
DELETE /api/v1/admin/users/{user_id}/platform-roles/{role_id}
```

Нельзя снять последнюю роль суперадмина (`last_superadmin`).
Требуется `roles.manage_platform`.

## 8. Платформенные роли

```http
GET    /api/v1/admin/platform-roles
POST   /api/v1/admin/platform-roles
PATCH  /api/v1/admin/platform-roles/{role_id}
DELETE /api/v1/admin/platform-roles/{role_id}
```

```json
{
  "code": "moderator_listings",
  "name": "Модератор объявлений",
  "permissions": ["listings.moderate", "complaints.handle"]
}
```

Ограничения:

- системную роль удалить нельзя (`system_role_immutable`);
- роль, назначенную пользователям, нельзя удалить (`role_in_use`);
- код роли уникален;
- права — только из списка `PLATFORM_PERMISSIONS`.

## 9. Каталог

```http
GET    /api/v1/admin/catalog/categories
POST   /api/v1/admin/catalog/categories
PATCH  /api/v1/admin/catalog/categories/{category_id}
DELETE /api/v1/admin/catalog/categories/{category_id}
```

Создание:

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

Правила:

- максимум 3 уровня (`category_depth_exceeded`);
- нельзя создать цикл (`category_cycle`);
- нельзя удалить категорию с детьми (`category_has_children`) или
  объявлениями (`category_has_listings`);
- `allowed_types` ограничивает типы объявлений в категории;
- slug генерируется автоматически.

Атрибуты:

```http
POST   /api/v1/admin/catalog/categories/{category_id}/attributes
PATCH  /api/v1/admin/catalog/attributes/{attribute_id}
DELETE /api/v1/admin/catalog/attributes/{attribute_id}
```

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

- ключ уникален в рамках категории (`attribute_exists`);
- `enum` и `multi_enum` требуют непустой `options`;
- атрибуты наследуются потомками;
- удаление атрибута не удаляет значения из существующих объявлений — они
  просто перестают валидироваться.

## 10. Аудит

```http
GET /api/v1/admin/audit?actor_id=<uuid>&action=listing.block&entity_type=listing
```

Фиксируются:

- блокировка/разблокировка пользователей;
- выдача/снятие ролей;
- верификация организаций и документов;
- модерация и продвижение объявлений;
- обработка жалоб;
- изменения каталога, тарифов, ролей, настроек.

Поля: `actor_id`, `action`, `entity_type`, `entity_id`, `payload`, `ip`,
`created_at`. Журнал доступен только с `audit.view` и не редактируется через
API.

## 11. Настройки

```http
GET /api/v1/admin/settings
PUT /api/v1/admin/settings/{key}
```

```json
{"value": {"hours": 12}, "description": "SLA модерации"}
```

Требуется `settings.manage`. Используйте для операционных параметров, которые
не требуют перезапуска. Секреты и параметры подключения к БД/Redis в настройки
не выносите.

## 12. Ежедневный регламент

**Утро**

1. `GET /admin/stats` — оценить очереди.
2. Разобрать новые жалобы (`status=new`).
3. Проверить документы (`documents_pending`).
4. Начать модерацию объявлений (`status=pending`).

**В течение дня**

5. Отвечать на жалобы: `take` → проверка → `resolve`.
6. Проверять организации с уровнем `phone`/`inn`.
7. Назначать тарифы и продвижения по заявкам.
8. Блокировать явный спам и мошенничество.

**Вечер**

9. Убедиться, что очередь `pending` не превышает SLA.
10. Просмотреть `audit_logs` на подозрительные действия.
11. Зафиксировать инциденты и передачи смены.

Рекомендуемый SLA: объявления — 24 часа, жалобы — 24 часа, документы —
48 часов.

## 13. Типовые ситуации

| Ситуация | Действие |
|---|---|
| Дубликат объявления | Отклонить с причиной «дубль», при повторе — блокировка |
| Неверная категория | Отклонить, автор исправит |
| Контакты в описании | Отклонить с просьбой перенести в поля контактов |
| Мошенничество | Блокировка объявления + блокировка пользователя + `resolve` жалобы |
| Оскорбления | Блокировка объявления, при повторе — пользователя |
| Запрещённый товар | Блокировка, при повторе — пользователь |
| Организация без документов | Оставить уровень `phone`/`inn`, запросить документы |
| Нечитаемый документ | `reject` с комментарием |
| Спорная жалоба | `rejected` с пояснением, при сомнении — эскалация |
| Массовый спам | Блокировка аккаунтов, снижение лимитов, эскалация L2 |

## 14. Ошибки админ-API

| Код | Что делать |
|---|---|
| `mfa_required` | Пройти `/auth/totp/verify` |
| `permission_denied` | Нет нужного права — запросить роль |
| `token_expired` | Обновить токен через `/auth/refresh` |
| `cannot_block_self` | Нельзя блокировать себя |
| `cannot_block_superadmin` | Нужна роль суперадмина |
| `last_superadmin` | Нельзя снять последнюю роль суперадмина |
| `block_reason_required` | Указать причину |
| `rejection_reason_required` | Указать комментарий отказа |
| `listing_not_active` | Продвигать можно только активное |
| `plan_in_use` | Тариф назначен организациям |
| `role_in_use` | Роль назначена пользователям |
| `category_has_children` | Сначала удалить/перенести детей |
| `category_has_listings` | В категории есть объявления |

## 15. Безопасность

- Не передавайте TOTP-коды и секреты коллегам.
- Не используйте общий аккаунт: аудит фиксирует `actor_id`.
- Не копируйте персональные данные в тикеты и мессенджеры.
- Не отключайте TOTP и не повышайте права без согласования.
- При подозрении на компрометацию аккаунта — заблокировать, отозвать токены,
  сообщить L2/L3.
- Все действия администратора видны в `audit_logs`; журнал не удаляется.
