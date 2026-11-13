from __future__ import annotations

import logging
import uuid

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register ORM metadata)
from app.core.cache import cache
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.seed import seed_all

logging.getLogger().setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

# Keep the development default from producing short-key JWT warnings in tests.
settings.secret_key = "test-secret-key-with-at-least-32-bytes"


@pytest_asyncio.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def db(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db):
    settings.superadmin_telegram_id = 999001
    settings.superadmin_phone = "+79990000001"
    await seed_all(db)
    yield db


@pytest_asyncio.fixture
async def client(session_factory, seeded):
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache.use_client(fake)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http

    app.dependency_overrides.clear()
    await fake.aclose()
    cache.use_client(None)


async def login(client: AsyncClient, telegram_id: int, phone: str, name: str = "Тест") -> dict:
    start = await client.post("/api/v1/auth/telegram/start")
    assert start.status_code == 200, start.text
    token = start.json()["token"]

    confirm = await client.post(
        "/api/v1/auth/telegram/dev-confirm",
        json={
            "token": token,
            "telegram_id": telegram_id,
            "phone": phone,
            "first_name": name,
        },
    )
    assert confirm.status_code == 200, confirm.text

    poll = await client.post("/api/v1/auth/telegram/poll", json={"token": token})
    assert poll.status_code == 200, poll.text
    payload = poll.json()
    assert payload["status"] == "confirmed", payload
    return payload["tokens"]


def auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def admin_tokens(client: AsyncClient) -> dict:
    tokens = await login(client, 999001, "+79990000001", "Admin")
    assert tokens["requires_totp"] is True

    import pyotp

    setup = await client.post(
        "/api/v1/auth/totp/setup", headers=auth_headers(tokens)
    )
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]

    enabled = await client.post(
        "/api/v1/auth/totp/enable",
        headers=auth_headers(tokens),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert enabled.status_code == 200, enabled.text
    mfa = enabled.json()
    assert mfa["access_token"] != tokens["access_token"]
    return mfa


@pytest.fixture
def unique_phone() -> str:
    suffix = uuid.uuid4().int % 10_000_000
    return f"+7999{suffix:07d}"
