import json
import logging
import time
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class Cache:
    """Small Redis wrapper with an in-process fallback.

    Redis is the production backend. The fallback exists so the app can boot for
    local smoke checks without Redis; it is never shared between processes.
    """

    def __init__(self) -> None:
        self._redis: Any = None
        self._memory: dict[str, tuple[float, str]] = {}

    async def connect(self) -> None:
        if self._redis is not None:
            return
        try:
            from redis.asyncio import from_url

            client = from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            self._redis = client
            logger.info("Redis connected")
        except Exception as exc:  # pragma: no cover - depends on environment
            self._redis = None
            logger.warning("Redis unavailable, using in-memory cache: %s", exc)

    async def close(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
        self._redis = None
        self._memory.clear()

    def use_client(self, client: Any) -> None:
        """Inject a client (used by tests with fakeredis)."""
        self._redis = client

    async def ping(self) -> bool:
        if self._redis is None:
            return False
        try:
            return bool(await self._redis.ping())
        except Exception:
            return False

    async def get(self, key: str) -> str | None:
        if self._redis is not None:
            return await self._redis.get(key)
        item = self._memory.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at and expires_at < time.monotonic():
            self._memory.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: str, ttl: int | None = None) -> None:
        if self._redis is not None:
            if ttl:
                await self._redis.set(key, value, ex=ttl)
            else:
                await self._redis.set(key, value)
            return
        expires_at = time.monotonic() + ttl if ttl else 0.0
        self._memory[key] = (expires_at, value)

    async def delete(self, key: str) -> None:
        if self._redis is not None:
            await self._redis.delete(key)
            return
        self._memory.pop(key, None)

    async def delete_prefix(self, prefix: str) -> None:
        if self._redis is not None:
            async for key in self._redis.scan_iter(match=f"{prefix}*"):
                await self._redis.delete(key)
            return
        for key in [k for k in self._memory if k.startswith(prefix)]:
            self._memory.pop(key, None)

    async def incr(self, key: str, ttl: int) -> int:
        if self._redis is not None:
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.ttl(key)
            count, current_ttl = await pipe.execute()
            if current_ttl < 0:
                await self._redis.expire(key, ttl)
            return int(count)
        item = self._memory.get(key)
        now = time.monotonic()
        if item and (not item[0] or item[0] > now):
            count = int(item[1]) + 1
            self._memory[key] = (item[0], str(count))
            return count
        self._memory[key] = (now + ttl, "1")
        return 1

    async def get_json(self, key: str) -> Any | None:
        raw = await self.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        await self.set(key, json.dumps(value, ensure_ascii=False, default=str), ttl)


cache = Cache()
