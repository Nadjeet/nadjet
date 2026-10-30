"""Redis fixed-window rate limiter for public (unauthenticated) endpoints (FR-CIT-004)."""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis


async def hit(redis: Redis, key: str, *, window_s: int) -> int:
    """Count one hit in the current window and return the count (window starts at hit 1)."""
    pipe = redis.pipeline(transaction=True)
    pipe.set(key, 0, ex=window_s, nx=True)
    pipe.incr(key)
    results = await pipe.execute()
    return int(results[1])


def rate_limit(
    name: str, *, per_minute: int, window_s: int = 60
) -> Callable[[Request], Awaitable[None]]:
    """Dependency: 429 once a client IP exceeds ``per_minute`` hits in ``window_s`` seconds."""

    async def check(request: Request) -> None:
        redis: Redis | None = getattr(request.app.state, "redis", None)
        if redis is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Rate limiter unavailable")
        client = request.client.host if request.client else "unknown"
        count = await hit(redis, f"ratelimit:{name}:{client}", window_s=window_s)
        if count > per_minute:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests",
                headers={"Retry-After": str(window_s)},
            )

    return check
