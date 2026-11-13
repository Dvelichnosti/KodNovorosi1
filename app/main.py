from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.v1.router import router as api_router
from app.core.cache import cache
from app.core.config import settings
from app.core.database import Base, engine
from app.core.errors import register_exception_handlers
from app.models import *  # noqa: F401,F403  (register ORM metadata)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Backend API платформы B2B-объявлений **BizBoard** для малого и среднего бизнеса.

* Авторизация через Telegram deep-link с JWT (access 15 минут / refresh 30 дней).
* Организации, собственные роли и разрешения, верификация ИНН/документов.
* Каталог до 3 уровней с наследуемыми атрибутами.
* 8 типов объявлений, модерация, поиск, избранное, жалобы.
* Админ-API (`/api/v1/admin/*`) требует TOTP-подтверждения.

Контакты объявлений видны только авторизованным пользователям.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "Вход через Telegram, JWT, TOTP."},
    {"name": "users", "description": "Профиль текущего пользователя."},
    {"name": "organizations", "description": "Организации, участники, роли, верификация."},
    {"name": "catalog", "description": "Категории и атрибуты."},
    {"name": "listings", "description": "Объявления, модерация со стороны владельца."},
    {"name": "uploads", "description": "Загрузка изображений и документов."},
    {"name": "public", "description": "Публичный каталог организаций."},
    {"name": "meta", "description": "Справочники и тарифы."},
    {"name": "telegram", "description": "Telegram webhook."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await cache.connect()
    settings.media_path.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured (AUTO_CREATE_TABLES=true)")
    logger.info("%s %s started (env=%s)", settings.app_name, settings.app_version, settings.env)
    try:
        yield
    finally:
        await cache.close()
        await engine.dispose()
        logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=settings.cors_origin_list != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

settings.media_path.mkdir(parents=True, exist_ok=True)
app.mount(settings.media_url, StaticFiles(directory=str(settings.media_path)), name="media")

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", tags=["meta"], include_in_schema=False)
async def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_v1_prefix,
    }


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": settings.app_version}


@app.get("/ready", tags=["meta"])
async def ready() -> dict:
    database_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        database_ok = True
    except Exception as exc:  # pragma: no cover - depends on environment
        logger.warning("Readiness check: database unavailable: %s", exc)
    redis_ok = await cache.ping()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": database_ok,
        "redis": redis_ok,
        "cache_fallback": cache._redis is None,  # noqa: SLF001
    }
