# Развёртывание

## 1. Требования

| Компонент | Версия |
|---|---|
| Python | 3.12 |
| PostgreSQL | 16 |
| Redis | 7 |
| Docker / Compose | для контейнерного запуска |
| Reverse proxy | nginx, Caddy, Traefik или облачный LB |

Минимальные ресурсы для MVP:

- API: 2 vCPU, 2 ГБ RAM, 2–4 воркера Uvicorn;
- PostgreSQL: 2 vCPU, 4 ГБ RAM, SSD;
- Redis: 1 vCPU, 512 МБ RAM;
- диск под медиа: по объёму загрузок.

## 2. Переменные окружения

Скопируйте `.env.example` в `.env` и заполните значения.

| Переменная | Обязательна | По умолчанию | Назначение |
|---|---|---|---|
| `APP_NAME` | нет | `BizBoard API` | Название в OpenAPI |
| `APP_VERSION` | нет | `1.0.0` | Версия |
| `ENV` | да | `dev` | `production` включает production-проверки |
| `DEBUG` | да | `true` | В production — `false` |
| `SECRET_KEY` | да | — | JWT и шифрование TOTP, 32+ байта |
| `API_V1_PREFIX` | нет | `/api/v1` | Префикс API |
| `DATABASE_URL` | да | — | `postgresql+asyncpg://...` |
| `DATABASE_ECHO` | нет | `false` | SQL-логи |
| `REDIS_URL` | да | — | `redis://...` |
| `ACCESS_TOKEN_TTL_MINUTES` | нет | `15` | TTL access-токена |
| `REFRESH_TOKEN_TTL_DAYS` | нет | `30` | TTL refresh-токена |
| `LOGIN_SESSION_TTL_MINUTES` | нет | `10` | TTL сессии входа |
| `INVITATION_TTL_HOURS` | нет | `72` | TTL приглашения |
| `TELEGRAM_BOT_TOKEN` | да | — | Токен бота |
| `TELEGRAM_BOT_USERNAME` | да | — | Username без `@` |
| `TELEGRAM_WEBHOOK_SECRET` | да | — | Секрет вебхука |
| `CORS_ORIGINS` | да | `*` | Список origin через запятую |
| `MEDIA_ROOT` | нет | `media` | Каталог файлов |
| `MEDIA_URL` | нет | `/media` | URL статики |
| `MAX_UPLOAD_MB` | нет | `20` | Максимальный размер файла |
| `DEFAULT_LISTING_TTL_DAYS` | нет | `30` | Срок публикации |
| `PRIVATE_ACTIVE_LISTING_LIMIT` | нет | `3` | Лимит частного лица |
| `PROMOTIONS_SELF_SERVICE` | нет | `false` | Самостоятельное продвижение |
| `TOTP_ISSUER` | нет | `BizBoard` | Issuer в authenticator |
| `SUPERADMIN_TELEGRAM_ID` | нет | — | Суперадмин при seed |
| `SUPERADMIN_PHONE` | нет | — | Телефон суперадмина |
| `LOGIN_START_RATE_LIMIT` | нет | `10` | Лимит старта входа |
| `LOGIN_START_RATE_WINDOW` | нет | `60` | Окно, сек |
| `LOGIN_POLL_RATE_LIMIT` | нет | `60` | Лимит poll |
| `LOGIN_POLL_RATE_WINDOW` | нет | `60` | Окно, сек |
| `COMPLAINT_RATE_LIMIT` | нет | `5` | Лимит жалоб |
| `COMPLAINT_RATE_WINDOW` | нет | `3600` | Окно, сек |
| `UPLOAD_RATE_LIMIT` | нет | `30` | Лимит загрузок |
| `UPLOAD_RATE_WINDOW` | нет | `3600` | Окно, сек |
| `AUTO_CREATE_TABLES` | нет | `false` | Создавать таблицы при старте |

`MFA_TOKEN_TTL_MINUTES` присутствует в конфигурации как резерв под отдельные
краткоживущие MFA-токены; текущая реализация использует обычный access-токен с
claim `mfa=true`.

## 3. Docker Compose

```bash
cp .env.example .env
# отредактируйте .env
docker compose up --build -d
docker compose logs -f api
```

`docker-compose.yml` поднимает:

- `postgres:16-alpine` с volume `pgdata`;
- `redis:7-alpine` с AOF и volume `redisdata`;
- `api`, который при старте выполняет:
  ```sh
  alembic upgrade head
  python -m app.seed
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  ```

Медиа монтируется из `./media` в `/app/media`.

Остановка:

```bash
docker compose down          # без удаления данных
docker compose down -v       # удалить volumes (ОПАСНО)
```

## 4. Ручное развёртывание

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# заполните .env

alembic upgrade head
python -m app.seed

uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4
```

Для нескольких воркеров:

- Redis обязателен (общий кэш и rate limit);
- медиа должно быть общим (shared volume или object storage);
- миграции выполняются **один раз** до старта воркеров, не в каждом воркере.

## 5. Reverse proxy (nginx)

```nginx
upstream bizboard_api {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    client_max_body_size 25m;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    location / {
        proxy_pass http://bizboard_api;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }

    location /media/ {
        alias /srv/bizboard/media/;
        expires 7d;
        add_header Cache-Control "public";
    }
}
```

`X-Forwarded-For` важен для rate limit и аудита: приложение берёт первый IP из
заголовка.

## 6. Миграции и seed

```bash
alembic upgrade head
python -m app.seed
```

Seed идемпотентен:

- платформенные роли `superadmin`, `moderator`, `support`;
- тарифы `free`, `business`, `pro`;
- дерево категорий и атрибуты;
- возможности организаций;
- настройки платформы;
- суперадмин, если заданы `SUPERADMIN_TELEGRAM_ID` и `SUPERADMIN_PHONE`.

Повторный запуск не создаёт дубликаты.

## 7. Первый администратор

1. Задайте в `.env`:
   ```env
   SUPERADMIN_TELEGRAM_ID=123456789
   SUPERADMIN_PHONE=+79990000000
   ```
2. Выполните `python -m app.seed`.
3. Войдите через Telegram.
4. Вызовите `POST /api/v1/auth/totp/setup`.
5. Добавьте секрет в Google Authenticator / 1Password / Authy.
6. Вызовите `POST /api/v1/auth/totp/enable` с кодом.
7. Используйте полученный access-токен с `mfa=true` для админ-API.

## 8. Telegram webhook

```bash
python -m scripts.set_telegram_webhook https://api.example.com/api/v1/telegram/webhook
```

Проверка:

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Требования:

- публичный HTTPS-домен;
- корректный `TELEGRAM_WEBHOOK_SECRET`;
- заголовок `X-Telegram-Bot-Api-Secret-Token` проверяется приложением.

## 9. Периодические задачи

```bash
python -m scripts.expire_listings
```

Рекомендуемый cron:

```cron
*/15 * * * * cd /srv/bizboard && .venv/bin/python -m scripts.expire_listings >> /var/log/bizboard/expire.log 2>&1
```

Дополнительно рекомендуется:

- ежедневный `pg_dump`;
- очистка старых `login_sessions` и `refresh_tokens`;
- ротация логов;
- проверка бэкапа.

## 10. Health checks

| Маршрут | Назначение |
|---|---|
| `GET /health` | Liveness: процесс жив |
| `GET /ready` | Readiness: БД и Redis |

`/ready`:

```json
{
  "status": "ok",
  "database": true,
  "redis": true,
  "cache_fallback": false
}
```

Если `database=false` — статус `degraded`, трафик направлять не следует.
Если `cache_fallback=true` — Redis недоступен, приложение работает на
внутрипроцессном кэше; для production это тревога.

Пример healthcheck в Kubernetes:

```yaml
livenessProbe:
  httpGet: { path: /health, port: 8000 }
  initialDelaySeconds: 10
readinessProbe:
  httpGet: { path: /ready, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
```

## 11. Мониторинг

Минимальный набор:

- доступность `/health` и `/ready`;
- доля 5xx;
- p95/p99 latency по маршрутам;
- количество `429`;
- размер очереди модерации (`listings_pending`);
- количество новых жалоб;
- ошибки Telegram webhook;
- свободное место на диске и в PostgreSQL;
- задержка Redis.

Логи — JSON или структурированный текст с уровнем, временем, методом и путём.
Не логируйте токены, TOTP-коды и тела `/auth/*`.

## 12. Производительность и масштабирование

Цель: **p95 поиска < 300 мс при 50 000 активных объявлений**.

Что уже сделано:

- GIN-индекс `ix_listings_fts` по `to_tsvector('russian', ...)`;
- GIN-индекс по JSONB `attributes`;
- составные индексы по статусу, категории, региону, организации;
- пагинация и ограничение `per_page <= 100`;
- кэш прав в Redis;
- отсутствие N+1 в основных выдачах за счёт `selectinload`/`joined`.

Что проверить на реальных данных:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM listings
WHERE status = 'active'
  AND deleted_at IS NULL
  AND (expires_at IS NULL OR expires_at > now())
  AND to_tsvector('russian', title || ' ' || description)
      @@ plainto_tsquery('russian', 'токарный')
ORDER BY published_at DESC
LIMIT 20;
```

Рекомендации:

- обновлять статистику (`ANALYZE listings`) после массовых загрузок;
- при росте до 500k+ рассмотреть materialized view или отдельный поисковый
  индекс;
- для атрибутных фильтров использовать GIN и избегать `CAST` по большим
  выборкам;
- кэшировать дерево категорий (уже кэшируется на 5 минут);
- вынести медиа в S3-совместимое хранилище;
- при необходимости — read-replica для поиска и админских отчётов.

## 13. Обновление и откат

Порядок:

1. Сделать бэкап БД.
2. Собрать новый образ/код.
3. Применить миграции: `alembic upgrade head`.
4. Запустить новый процесс.
5. Проверить `/health`, `/ready`, smoke-тесты.
6. Переключить трафик.

Откат:

1. Вернуть предыдущий образ/код.
2. Если миграция несовместима — `alembic downgrade -1`.
3. Проверить восстановление данных.

Не откатывайте миграции, которые удаляют данные, без бэкапа.

## 14. Медиа в production

MVP хранит файлы локально. Для нескольких инстансов это создаёт проблемы:

- файл, загруженный на одном инстансе, недоступен на другом;
- бэкап и очистка усложняются.

Рекомендация:

- S3/MinIO с private bucket для документов;
- public bucket/CDN для изображений и логотипов;
- подписанные URL для приватных документов;
- антивирусная проверка перед публикацией.

## 15. Чек-лист деплоя

- [ ] `.env` заполнен, секреты не в git.
- [ ] `ENV=production`, `DEBUG=false`.
- [ ] `SECRET_KEY` случайный, 32+ байта.
- [ ] PostgreSQL и Redis доступны только по private network.
- [ ] `alembic upgrade head` выполнена.
- [ ] `python -m app.seed` выполнен.
- [ ] Суперадмин создан, TOTP включён.
- [ ] Webhook Telegram установлен.
- [ ] Cron на `expire_listings` настроен.
- [ ] Бэкапы и мониторинг включены.
- [ ] HTTPS и CORS настроены.
- [ ] Проверены `/health`, `/ready`, `/docs`.
- [ ] Прогнаны smoke-тесты: вход, создание объявления, модерация, поиск.
