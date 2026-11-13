# Операционный регламент

Документ для дежурного инженера и администратора платформы.

## 1. Ежедневные проверки

| Проверка | Как | Норма |
|---|---|---|
| API жив | `GET /health` | `status=ok` |
| БД и Redis | `GET /ready` | `database=true`, `redis=true`, `cache_fallback=false` |
| Ошибки 5xx | мониторинг/логи | нет всплеска |
| Очередь модерации | `GET /admin/stats` | `listings_pending` в пределах SLA |
| Новые жалобы | `GET /admin/stats` | `complaints_new` разбираются |
| Документы | `GET /admin/stats` | `documents_pending` в пределах SLA |
| Бэкап | файл за прошлую ночь | есть, размер адекватен |
| Диск | `df -h`, размер БД | запас > 20% |
| Telegram webhook | `getWebhookInfo` | нет `last_error_message` |

## 2. Еженедельные проверки

- проверить `audit_logs` на подозрительные действия;
- просмотреть заблокированных пользователей;
- проверить тарифы и лимиты организаций;
- проверить старые приглашения и сессии;
- просмотреть 429/rate limit;
- проверить восстановление бэкапа на тестовом стенде (раз в месяц).

## 3. Запуск и остановка

### Docker Compose

```bash
docker compose up -d
docker compose ps
docker compose logs -f api
docker compose restart api
docker compose down
```

### Systemd (пример)

```ini
[Unit]
Description=BizBoard API
After=network.target postgresql.service redis.service

[Service]
User=bizboard
WorkingDirectory=/srv/bizboard
EnvironmentFile=/srv/bizboard/.env
ExecStart=/srv/bizboard/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now bizboard
systemctl status bizboard
journalctl -u bizboard -f
```

## 4. Миграции

Перед миграцией:

```bash
pg_dump --format=custom --file=/backups/bizboard-before-migration.dump "$DATABASE_URL"
alembic current
alembic history
```

Применение:

```bash
alembic upgrade head
```

Откат:

```bash
alembic downgrade -1
```

Если миграция блокирует таблицу:

1. оцените время блокировки;
2. выберите окно обслуживания;
3. для больших таблиц используйте `CREATE INDEX CONCURRENTLY` в отдельной
   миграции;
4. не запускайте тяжёлые миграции одновременно с пиком нагрузки.

## 5. Seed

```bash
python -m app.seed
```

Безопасно запускать повторно. Используется для:

- добавления новых ролей/тарифов/категорий;
- создания суперадмина;
- восстановления справочников.

Не удаляет пользовательские данные.

## 6. Бэкапы

### PostgreSQL

```bash
mkdir -p /backups
pg_dump --format=custom \
  --file=/backups/bizboard-$(date +%F-%H%M).dump \
  "$DATABASE_URL"
```

Хранение: 14 дней. Раз в месяц — архив на холодное хранилище.

### Восстановление

```bash
# в отдельную БД, чтобы не сломать production
createdb bizboard_restore
pg_restore --dbname=bizboard_restore /backups/bizboard-2026-11-13.dump
```

Проверьте:

- количество пользователей и объявлений;
- последние записи `audit_logs`;
- целостность внешних ключей;
- работоспособность приложения на восстановленной копии.

### Медиа

```bash
rsync -a --delete /srv/bizboard/media/ /backups/media/
```

Для S3 — включите versioning и lifecycle policy.

## 7. Периодические задачи

### Истечение объявлений

```bash
python -m scripts.expire_listings
```

Cron:

```cron
*/15 * * * * cd /srv/bizboard && .venv/bin/python -m scripts.expire_listings >> /var/log/bizboard/expire.log 2>&1
```

Проверка:

```sql
SELECT count(*) FROM listings
WHERE status = 'active' AND expires_at < now();
```

Должно быть близко к нулю после запуска.

### Очистка (рекомендуется добавить)

```sql
DELETE FROM login_sessions WHERE expires_at < now() - interval '7 days';
DELETE FROM refresh_tokens
WHERE expires_at < now() - interval '90 days'
   OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '90 days');
```

Перед удалением — бэкап.

## 8. Telegram

### Установка webhook

```bash
python -m scripts.set_telegram_webhook https://api.example.com/api/v1/telegram/webhook
```

### Проверка

```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Признаки проблем:

- `last_error_message` не пустой;
- `pending_update_count` растёт;
- `last_error_date` свежая.

### Переустановка

```bash
python -m scripts.set_telegram_webhook https://api.example.com/api/v1/telegram/webhook
```

Если секрет изменился — обновите `TELEGRAM_WEBHOOK_SECRET` и переустановите
webhook.

## 9. Модерация: SLA и очередь

Рекомендуемый SLA:

- объявления — 24 часа;
- жалобы — 24 часа;
- документы — 48 часов.

Очередь:

```http
GET /api/v1/admin/listings?status=pending
GET /api/v1/admin/complaints?status=new
GET /api/v1/admin/organizations?verification_level=phone
```

Порядок:

1. проверить полноту и категорию;
2. проверить контакты и признаки мошенничества;
3. одобрить, отклонить или заблокировать с причиной;
4. при жалобе — взять в работу, проверить, решить;
5. при документе — одобрить или отклонить с комментарием.

## 10. Типовые инциденты

### 10.1. `/ready` показывает `database=false`

1. Проверить PostgreSQL: `pg_isready`, логи, диск.
2. Проверить `DATABASE_URL` и сетевую доступность.
3. Проверить пул соединений.
4. Не перезапускать API вслепую — сначала восстановить БД.

### 10.2. `/ready` показывает `cache_fallback=true`

1. Проверить Redis: `redis-cli ping`.
2. Проверить `REDIS_URL`, память, eviction policy.
3. Понимать последствия: rate limit и кэш прав не общие между воркерами.
4. После восстановления перезапустить API, чтобы подключиться к Redis.

### 10.3. Массовые 429

1. Проверить, не атака ли это.
2. Проверить, не слишком ли строгие лимиты.
3. Временно увеличить лимиты через env и перезапуск.
4. Включить защиту на proxy/CDN.

### 10.4. Очередь модерации растёт

1. Проверить `listings_pending`.
2. Подключить дополнительных модераторов.
3. Временно увеличить SLA-уведомление.
4. Проверить, не спам ли это — блокировать аккаунты.

### 10.5. Ошибки Telegram webhook

1. `getWebhookInfo`.
2. Проверить публичный HTTPS и сертификат.
3. Проверить `TELEGRAM_WEBHOOK_SECRET`.
4. Проверить логи `telegram update processing failed`.
5. Переустановить webhook.

### 10.6. Утечка или компрометация токена

1. Заблокировать пользователя или отозвать все токены.
2. Проверить `refresh_tokens` и `audit_logs`.
3. При компрометации `SECRET_KEY`:
   - сменить ключ;
   - все сессии станут недействительны;
   - TOTP-секреты потребуют перевыпуска.
4. Уведомить ответственных.

### 10.7. Ошибка 500 после деплоя

1. Посмотреть traceback в логах.
2. Проверить, применены ли миграции.
3. Проверить совместимость схемы и кода.
4. Откатить образ и, при необходимости, миграцию.
5. Восстановить из бэкапа, если данные повреждены.

## 11. Полезные SQL-запросы

```sql
-- Активные объявления по регионам
SELECT region, count(*) FROM listings
WHERE status = 'active' AND deleted_at IS NULL
GROUP BY region ORDER BY count(*) DESC;

-- Очередь модерации
SELECT id, title, submitted_at FROM listings
WHERE status = 'pending' AND deleted_at IS NULL
ORDER BY submitted_at NULLS LAST;

-- Просроченные, но ещё активные
SELECT count(*) FROM listings
WHERE status = 'active' AND expires_at < now();

-- Жалобы по статусам
SELECT status, count(*) FROM complaints GROUP BY status;

-- Организации без тарифа
SELECT id, name FROM organizations WHERE plan_id IS NULL;

-- Пользователи с платформенными ролями
SELECT u.id, u.phone, r.code
FROM users u
JOIN user_platform_roles upr ON upr.user_id = u.id
JOIN platform_roles r ON r.id = upr.role_id;

-- Размер БД
SELECT pg_size_pretty(pg_database_size(current_database()));

-- Размер таблиц
SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;
```

## 12. Обслуживание

### Окно обслуживания

1. Уведомить пользователей.
2. Перевести API в режим read-only или остановить.
3. Сделать бэкап.
4. Применить миграции/обновление.
5. Запустить, проверить `/ready`.
6. Прогнать smoke-тесты.
7. Вернуть трафик.

### Ротация логов

```bash
logrotate -f /etc/logrotate.d/bizboard
```

Настройте `daily`, `rotate 14`, `compress`, `missingok`, `notifempty`.

### Обновление зависимостей

```bash
pip install -r requirements-dev.txt --upgrade
python -m pytest
python -m ruff check app scripts tests alembic
```

Обновляйте зависимости в отдельной ветке и проверяйте на staging.

## 13. Контакты и эскалация

| Уровень | Кто | Когда |
|---|---|---|
| L1 | Дежурный инженер | Мониторинг, рестарт, типовые инциденты |
| L2 | Backend-разработчик | Ошибки кода, миграции, данные |
| L3 | Архитектор/владелец продукта | Изменение бизнес-правил, безопасность |

При инциденте фиксируйте:

- время начала и обнаружения;
- затронутые функции;
- действия и результат;
- root cause;
- план предотвращения.
