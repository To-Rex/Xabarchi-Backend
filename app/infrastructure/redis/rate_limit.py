"""Fixed-window rate limiting on Redis (INCR + EXPIRE).

Fail-open by design: if Redis is unreachable we log a warning and allow the
request — availability of the API is worth more than strict limiting during
a Redis outage.
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError

from app.core.exceptions import RateLimitError
from app.infrastructure.redis.client import get_redis

logger = logging.getLogger(__name__)


async def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    """Count a hit against ``key``; raise :class:`RateLimitError` when over.

    Fixed window: the first INCR in a window sets the TTL; the counter simply
    expires at the window boundary.
    """
    redis_key = f"ratelimit:{key}"
    try:
        client = get_redis()
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, window_seconds)
    except (RedisError, OSError) as exc:
        logger.warning("Rate limiter unavailable (fail-open) for %s: %s", key, exc)
        return
    if count > limit:
        raise RateLimitError(
            f"Rate limit exceeded: {limit} requests per {window_seconds}s"
        )
