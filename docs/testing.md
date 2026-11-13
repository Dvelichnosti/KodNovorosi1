# Тестирование

## 1. Подход

Тесты проверяют **поведение API и доменные правила**, а не внутреннюю
реализацию. Каждый тест поднимает приложение целиком через `httpx.ASGITransport`
и работает с настоящими роутерами, зависимостями, сериализаторами и
обработчиками ошибок.

Инфраструктура подменяется:

| Компонент | В тестах |
|---|---|
| PostgreSQL | in-memory SQLite (`sqlite+aiosqlite://`, `StaticPool`) |
| Redis | `fakeredis.aioredis.FakeRedis` |
| Telegram Bot API | `POST /auth/telegram/dev-confirm` (только dev) |
| TOTP | `pyotp.TOTP(secret).now()` |
| Внешние HTTP-вызовы | не выполняются |

Тесты не требуют Docker, PostgreSQL, Redis, сети и реального Telegram-бота.

## 2. Запуск

```bash
# все тесты
python -m pytest -q

# подробный вывод
python -m pytest -v

# один файл
python -m pytest tests/test_flow.py -q

# один тест
python -m pytest tests/test_flow.py::test_full_listing_lifecycle_and_contacts_visibility -q

# с логами
python -m pytest -q -s --log-cli-level=INFO

# остановиться на первом падении
python -m pytest -q -x

# только упавшие в прошлый раз
python -m pytest -q --lf
```

Ожидаемый результат на текущей кодовой базе: **18 passed**.

## 3. Конфигурация pytest

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`asyncio_mode = "auto"` позволяет писать `async def test_...` без декораторов.

## 4. Фикстуры

Все фикстуры находятся в `tests/conftest.py`.

| Фикстура | Назначение |
|---|---|
| `engine` | Новый in-memory SQLite на каждый тест, схема из `Base.metadata.create_all` |
| `session_factory` | `async_sessionmaker` с `expire_on_commit=False` |
| `db` | Одна `AsyncSession` для прямых запросов в тесте |
| `seeded` | Заполняет БД через `seed_all`: роли, тарифы, каталог, настройки, суперадмин |
| `client` | `AsyncClient` поверх ASGI-приложения, подменяет `get_db` и Redis |
| `unique_phone` | Гарантированно уникальный телефон `+7999XXXXXXX` |

Хелперы:

| Функция | Назначение |
|---|---|
| `login(client, telegram_id, phone, name)` | Полный вход через `start → dev-confirm → poll`, возвращает `TokenPair` |
| `auth_headers(tokens)` | Заголовок `Authorization: Bearer ...` |
| `admin_tokens(client)` | Вход суперадмина + `totp/setup` + `totp/enable`, возвращает токены с `mfa=true` |

Изоляция: каждый тест получает новую БД в памяти, поэтому порядок тестов и
параллельный запуск не влияют на результат. `fakeredis` очищается после
закрытия клиента.

## 5. Матрица покрытия

| Файл | Что проверяется |
|---|---|
| `test_inn.py` | Контрольная сумма ИНН (10 и 12 цифр), длина по типу организации, нормализация и валидация телефона |
| `test_catalog.py` | Максимум 3 уровня категорий, наследование обязательных атрибутов, отказ на неизвестный атрибут |
| `test_flow.py` | Полный жизненный цикл объявления, видимость контактов, обязательность TOTP для админ-API, лимит публикаций частного лица |
| `test_organizations.py` | Кастомные роли, приглашения, жизненный цикл сотрудника, несовпадение Telegram-ID, отзыв приглашения, эскалация прав, передача владения, верификация ИНН и дубликаты |
| `test_complaints_favorites.py` | Избранное, жалобы, запрет жалоб на своё объявление, обработка жалобы модератором |
| `test_admin_smoke.py` | Управление каталогом, тарифами, платформенными ролями и пользователями через админ-API |

### Покрытые сценарии

- вход через Telegram и выдача пары токенов;
- `requires_totp=true` для платформенного пользователя;
- `403 mfa_required` при обращении в админ-API без TOTP;
- ротация refresh-токена и обнаружение повторного использования;
- создание организации и назначение системных ролей;
- приглашение по `telegram_id` и по ссылке;
- запрет эскалации прав и изменения владельца;
- проверка ИНН и уникальность;
- создание объявления, `submit`, `approve`, публичный поиск;
- скрытие контактов без авторизации и показ после входа;
- лимит активных объявлений частного лица;
- избранное и жалобы;
- модерация жалобы (`take` → `resolve`);
- CRUD категорий, атрибутов, тарифов, платформенных ролей;
- блокировка пользователя и выдача платформенной роли.

### Что пока не покрыто автотестами

- реальный PostgreSQL и поведение `tsvector`/GIN;
- реальный Redis (используется `fakeredis`);
- загрузка файлов (`/uploads`) и раздача `/media`;
- Telegram webhook (обработка обновлений);
- `scripts/expire_listings` и `scripts/set_telegram_webhook`;
- нагрузочные и конкурентные сценарии;
- фронтенд/браузерные сценарии (проект — только backend).

Для этих участков обязательны ручные smoke-тесты на staging (см.
[deployment.md](deployment.md#15-чек-лист-деплоя)).

## 6. Как писать новый тест

```python
from tests.conftest import auth_headers, login


async def test_my_feature(client, unique_phone):
    tokens = await login(client, telegram_id=555001, phone=unique_phone)
    headers = auth_headers(tokens)

    response = await client.get("/api/v1/listings", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 0
```

Правила:

1. Называйте тест как утверждение: `test_category_tree_is_limited_to_three_levels`.
2. Проверяйте и статус, и тело ответа.
3. Для админ-сценариев используйте `admin_tokens(client)`.
4. Не полагайтесь на порядок тестов и общее состояние.
5. Для проверки БД используйте фикстуру `db` и `select(...)`.
6. Не вызывайте реальные внешние сервисы.
7. Если тест требует нового справочника — добавьте его в `seed_all`, а не в тест.

### Пример теста админ-сценария

```python
from tests.conftest import admin_tokens


async def test_admin_can_block_user(client, unique_phone):
    tokens = await admin_tokens(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    user = await client.post(
        "/api/v1/auth/telegram/start",
    )
    # ... создать пользователя через login() и получить его id

    response = await client.post(
        f"/api/v1/admin/users/{user_id}/block",
        headers=headers,
        json={"reason": "Спам"},
    )
    assert response.status_code == 200
```

## 7. Отладка

| Симптом | Причина | Решение |
|---|---|---|
| `MissingGreenlet` | Ленивая загрузка после коммита | `selectinload`/`joined` в запросе |
| `no such table` | Схема не создана | Проверьте фикстуру `engine` |
| `RuntimeError: Event loop is closed` | Неверный scope фикстуры | Используйте `pytest_asyncio.fixture` |
| `403 mfa_required` | Нет TOTP | `admin_tokens(client)` |
| `410 login_used` | Повторный poll | Создайте новую сессию входа |
| Тест проходит локально, падает в CI | Общее состояние/время | Проверьте изоляцию и TOTP-окно |

Просмотр SQL:

```python
engine = create_async_engine(..., echo=True)
```

или `DATABASE_ECHO=true` для приложения.

## 8. Линтер и компиляция

```bash
python -m ruff check app scripts tests alembic
python -m ruff check app scripts tests alembic --fix
python -m compileall -q app scripts alembic tests
```

Ruff проверяет импорты, неиспользуемые переменные, стиль и потенциальные
ошибки. `compileall` ловит синтаксические ошибки в файлах, которые не
импортируются тестами.

## 9. CI (рекомендуемый pipeline)

```yaml
stages:
  - lint
  - test

lint:
  script:
    - pip install -r requirements-dev.txt
    - python -m ruff check app scripts tests alembic
    - python -m compileall -q app scripts alembic tests

test:
  script:
    - pip install -r requirements-dev.txt
    - python -m pytest -q
```

Для интеграционного этапа с PostgreSQL добавьте сервис `postgres:16` и
прогоните миграции:

```bash
DATABASE_URL=postgresql+asyncpg://... alembic upgrade head
DATABASE_URL=postgresql+asyncpg://... python -m pytest -q
```

## 10. Ограничения

- SQLite не воспроизводит PostgreSQL FTS, JSONB-операторы и поведение
  блокировок. Тесты поиска проверяют логику фильтров, но не производительность.
- `fakeredis` не воспроизводит кластер, eviction и сетевые задержки.
- Тесты не проверяют реальную доставку Telegram-сообщений.
- Нет тестов на конкурентную ротацию refresh-токенов под нагрузкой.
- Нет измерения p95 поиска; цель < 300 мс проверяется на staging с реальным
  объёмом данных.

Перед production обязательны:

1. прогон миграций на копии реальной БД;
2. smoke-тест входа через реальный Telegram;
3. проверка загрузки и раздачи файлов;
4. нагрузочный тест поиска на 50 000 объявлений;
5. проверка cron `expire_listings`.
