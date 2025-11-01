"""Redis-backed per-IP rate limiting for FastAPI endpoints.

Design:
- Key format: rl:{endpoint_key}:{client_ip}
- On request: INCR → if 1 then EXPIRE window; if value > quota → raise 429
- Fallback: if Redis unavailable, allow request and log a warning
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: Any | None = (
    None  # lazy-initialized; connection pool is internal to client
)


def _get_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        # Use asyncio Redis client to avoid blocking the event loop
        from redis.asyncio import Redis  # type: ignore

        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        return _redis_client
    except Exception as exc:  # pragma: no cover - only hit if import fails
        logger.warning("redis_client_init_failed", extra={"error": str(exc)})
        return None


def _extract_client_ip(request: Request) -> str:
    # Respect X-Forwarded-For if present (behind proxy/load balancer)
    xff = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if xff:
        # First IP in the list is the client IP
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    client = request.client
    return client.host if client else "unknown"


def rate_limit(
    endpoint_key: str,
    *,
    requests: int | None = None,
    window_seconds: int | None = None,
) -> Callable[[Request], Awaitable[None]]:
    """Create a FastAPI dependency that enforces a Redis-backed rate limit.

    Args:
        endpoint_key: Stable identifier for this endpoint (e.g., "ticker_articles").
        requests: Max requests within the window. Defaults to settings.rl_requests_per_minute.
        window_seconds: Window size in seconds. Defaults to settings.rl_window_seconds.
    """

    max_requests = requests or settings.rl_requests_per_minute
    window = window_seconds or settings.rl_window_seconds

    async def _dependency(request: Request) -> None:
        client_ip = _extract_client_ip(request)
        key = f"rl:{endpoint_key}:{client_ip}"

        client = _get_client()
        if client is None:
            # Fail-open if Redis is not available
            logger.warning(
                "rate_limit_fallback_allow",
                extra={"endpoint": endpoint_key, "ip": client_ip},
            )
            return

        try:
            # Atomically increment; set TTL on first hit in the window
            current = await client.incr(key)
            if current == 1:
                await client.expire(key, window)

            if current > max_requests:
                ttl = await client.ttl(key)
                retry_after = ttl if isinstance(ttl, int) and ttl > 0 else window
                logger.warning(
                    "rate_limit_block",
                    extra={
                        "endpoint": endpoint_key,
                        "ip": client_ip,
                        "quota": max_requests,
                        "retry_after": retry_after,
                    },
                )
                # Raise HTTP 429 with Retry-After header and JSON body
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Too Many Requests",
                        "retry_after": retry_after,
                    },
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except Exception as exc:
            # On Redis errors, fail-open but log the error
            logger.error(
                "rate_limit_redis_error",
                extra={"endpoint": endpoint_key, "ip": client_ip, "error": str(exc)},
            )
            return

    return _dependency
