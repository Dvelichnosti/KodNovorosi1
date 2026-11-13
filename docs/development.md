# Разработка

## 1. Требования

- Python 3.12
- PostgreSQL 16 (для полноценной работы)
- Redis 7 (для кэша и rate limit)
- Docker + Compose (опционально)
- Git

Для тестов PostgreSQL и Redis не нужны: используются `aiosqlite` и `fakeredis`.

## 2. Первичная настройка

```bash
git clone <repo>
cd backend-stankov

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt

cp .env.example .env
```

Заполните `.env`:

```env
ENV=dev
DEBUG=true
SECRET_KEY=dev-secret-key-with-at-least-32-bytes
DATABASE_URL=postgresql+asyncpg://bizboard:bizboard@localhost:5432/bizboard
REDIS_URL=redis://localhost:6379/0
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
```

Для быстрого старта без PostgreSQL/Redis:

```env
DATABASE_URL=sqlite+aiosqlite:///./dev.db
AUTO_CREATE_TABLES=true
```

В этом режиме таблицы создаются при старте, Redis заменяется
внутрипроцессным кэшем. **Не используйте это в production.**

## 3. База данных

### PostgreSQL через Docker

```bash
docker compose up -d postgres redis
alembic upgrade head
python -m app.seed
```

### Локальный PostgreSQL

```bash
createdb bizboard
alembic upgrade head
python -m app.seed
```

### SQLite для быстрой проверки

```bash
export DATABASE_URL=sqlite+aiosqlite:///./dev.db
export AUTO_CREATE_TABLES=true
python -m app.seed
```

Ограничения SQLite:

- нет JSONB (используется JSON);
- нет `tsvector` — поиск через `ILIKE`;
- нет `NULLS LAST` в старых версиях;
- миграция создаёт PostgreSQL-индекс только на PostgreSQL.

## 4. Запуск

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Проверка:

- <http://localhost:8000/health>
- <http://localhost:8000/ready>
- <http://localhost:8000/docs>
- <http://localhost:8000/redoc>
- <http://localhost:8000/openapi.json>

## 5. Тесты

```bash
python -m pytest -q
```

Подробнее: [testing.md](testing.md).

Быстрый прогон одного файла:

```bash
python -m pytest tests/test_flow.py -q
python -m pytest tests/test_organizations.py -q
```

С выводом логов:

```bash
python -m pytest -q -s --log-cli-level=INFO
```

## 6. Линтер и компиляция

```bash
python -m ruff check app scripts tests alembic
python -m ruff check app scripts tests alembic --fix
python -m compileall -q app scripts alembic tests
```

Правила Ruff заданы в `pyproject.toml`. Импорты сортируются автоматически.

## 7. Структура и соглашения

### Слои

```text
api → services → models
      ↓
    core
```

- Роутер: зависимости, валидация, вызов сервиса, сериализация.
- Сервис: бизнес-правила, транзакции, доменные ошибки.
- Модель: только поля и связи.
- Схема: Pydantic-контракт.
- Core: инфраструктура без доменной логики.

### Именование

- Python: `snake_case`, классы `PascalCase`.
- Роутеры: `app/api/v1/<domain>.py`.
- Сервисы: `app/services/<domain>_service.py`.
- Схемы: `app/schemas/<domain>.py`.
- Ошибки: `AppError(message, status_code=..., code="snake_case")`.
- Коды ошибок — стабильные, на английском, в `snake_case`.

### Транзакции

- Сервис сам вызывает `await db.commit()`.
- После коммита не полагайтесь на ленивую загрузку связей: используйте
  `selectinload`/`joined` или повторный `get_*`.
- Для полей с `onupdate=func.now()` после коммита может потребоваться
  `await db.refresh(obj, attribute_names=["updated_at"])`.
- Аудит пишется в той же транзакции, что и изменение.

### Валидация

- Формат и границы — в Pydantic-схемах.
- Бизнес-правила — в сервисах.
- Неизвестные поля Pydantic по умолчанию игнорирует; для строгого контракта
  задавайте `model_config = ConfigDict(extra="forbid")`.

## 8. Как добавить эндпоинт

1. Добавьте схему запроса/ответа в `app/schemas/`.
2. Реализуйте бизнес-логику в `app/services/`.
3. Создайте роутер в `app/api/v1/` или `app/api/v1/admin/`.
4. Подключите роутер:
   - публичный — `app/api/v1/router.py`;
   - админский — `app/api/v1/admin/router.py`.
5. Добавьте тест.
6. Проверьте OpenAPI: `python -m scripts.export_openapi`.

Пример:

```python
from fastapi import APIRouter, Depends

from app.api.deps import DB, AuthContext, get_auth
from app.schemas.common import Message
from app.services import my_service

router = APIRouter(prefix="/my", tags=["my"])


@router.post("/action", response_model=Message)
async def action(
    auth: AuthContext = Depends(get_auth),
    db: DB = None,
) -> Message:
    await my_service.do_action(db, auth.user)
    return Message(message="Готово")
```

## 9. Как добавить миграцию

```bash
alembic revision -m "add table x"
```

Отредактируйте файл в `alembic/versions/`. Реализуйте `upgrade()` и
`downgrade()`.

```python
def upgrade() -> None:
    op.create_table(
        "x",
        sa.Column("id", sa.String(32), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("x")
```

Проверка на SQLite:

```bash
DATABASE_URL=sqlite+aiosqlite:///./tmp.db alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./tmp.db alembic downgrade base
```

Для PostgreSQL-специфичных операций проверяйте диалект:

```python
bind = op.get_bind()
if bind.dialect.name == "postgresql":
    op.execute("CREATE INDEX ... USING gin (...)")
```

## 10. Как добавить разрешение

1. Добавьте код в `ORG_PERMISSIONS` или `PLATFORM_PERMISSIONS`
   (`app/core/permissions.py`).
2. При необходимости обновите шаблоны ролей.
3. Используйте код в `require_org_permission` / `require_platform_permission`.
4. Обновите документацию и тесты.
5. Помните: существующие роли не получат новое право автоматически.

## 11. Работа с TOTP в разработке

- `POST /auth/totp/setup` возвращает секрет.
- Сгенерировать код:

```python
import pyotp
print(pyotp.TOTP(secret).now())
```

- В тестах используется `tests/conftest.py::admin_tokens`.
- `dev-confirm` работает только при `DEBUG=true` и `ENV != production`.

## 12. Работа с Telegram

Без бота используйте dev-подтверждение:

```bash
curl -X POST http://localhost:8000/api/v1/auth/telegram/dev-confirm \
  -H "Content-Type: application/json" \
  -d '{"token":"<token>","telegram_id":123,"phone":"+79991234567","first_name":"Тест"}'
```

С ботом:

1. Укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_BOT_USERNAME`.
2. Поднимите публичный HTTPS (ngrok, cloudflared).
3. Установите webhook:
   ```bash
   python -m scripts.set_telegram_webhook https://<host>/api/v1/telegram/webhook
   ```

## 13. Частые проблемы

### `MissingGreenlet`

Причина: ленивая загрузка связи после коммита в async-сессии.
Решение: `selectinload`/`joined` в запросе или повторный запрос объекта.

### `no such table`

Причина: не применены миграции или не включён `AUTO_CREATE_TABLES`.
Решение: `alembic upgrade head` или `AUTO_CREATE_TABLES=true` для SQLite.

### Redis unavailable

Приложение продолжит работу на memory-кэше. Для проверки Redis:

```bash
redis-cli ping
```

### `SECRET_KEY` слишком короткий

PyJWT выдаёт `InsecureKeyLengthWarning`. Используйте 32+ байта.

### TOTP не принимается

- проверьте системное время;
- код действует 30 секунд, допускается ±1 шаг;
- убедитесь, что используется тот же секрет;
- при смене `SECRET_KEY` секрет нужно перевыпустить.

### Ошибка `database is locked` (SQLite)

SQLite не предназначен для параллельных тестов/нагрузки. Используйте
PostgreSQL или in-memory SQLite с `StaticPool` (как в тестах).

## 14. Git и ревью

Рекомендуемый поток:

```bash
git checkout -b feature/my-change
# изменения
python -m pytest -q
python -m ruff check app scripts tests alembic
git add .
git commit -m "feat: add my change"
```

Правила:

- один PR — одна логическая задача;
- миграции и код — в одном PR;
- тесты обязательны для новых правил;
- не коммитьте `.env`, `media`, `*.db`, `__pycache__`;
- в описании PR укажите влияние на API и данные.

## 15. Полезные команды

```bash
# все тесты
python -m pytest -q

# только упавшие
python -m pytest -q --lf

# покрытие (если установлен pytest-cov)
python -m pytest --cov=app --cov-report=term-missing

# OpenAPI
python -m scripts.export_openapi

# seed
python -m app.seed

# истечение объявлений
python -m scripts.expire_listings

# webhook
python -m scripts.set_telegram_webhook https://host/api/v1/telegram/webhook
```
