"""Lazy singleton redis.asyncio client.

The client is created on first use (not at import time) so that importing the
app never requires a live Redis, and closed once at application shutdown.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return the process-wide Redis client, creating it on first call.

    ``decode_responses=True`` so every command returns ``str`` — all payloads
    we store/publish are JSON text.
    """
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    """Close the singleton client (called from the app shutdown hook)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
