from app.core.cache import cache
from app.core.errors import AppError


async def enforce_rate_limit(key: str, limit: int, window: int) -> None:
    if limit <= 0:
        return
    count = await cache.incr(f"ratelimit:{key}", window)
    if count > limit:
        raise AppError(
            "Слишком много запросов. Попробуйте позже.",
            status_code=429,
            code="rate_limited",
            details={"retry_after": window},
            headers={"Retry-After": str(window)},
        )
