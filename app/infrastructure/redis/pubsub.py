"""Per-user realtime events over Redis pub/sub.

Every user has one channel (``user:<uuid>``); the WebSocket route subscribes
to it and relays messages to the browser. Publishing is best-effort: a dead
Redis must never fail the HTTP request that triggered the event.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

import orjson
from redis.exceptions import RedisError

from app.infrastructure.redis.client import get_redis

logger = logging.getLogger(__name__)


def _channel(user_id: uuid.UUID | str) -> str:
    return f"user:{user_id}"


async def publish_event(user_id: uuid.UUID | str, event: str, data: dict[str, Any]) -> None:
    """PUBLISH a typed event to the user's channel; best-effort (never raises).

    Wire format matches what the frontend WS client expects:
    ``{"type": "notification", "event": "<event>", "data": {...}}``.
    """
    payload = orjson.dumps({"type": "notification", "event": event, "data": data})
    try:
        await get_redis().publish(_channel(user_id), payload.decode("utf-8"))
    except (RedisError, OSError) as exc:
        logger.warning("Redis publish failed for %s (%s): %s", _channel(user_id), event, exc)


async def subscribe_user(user_id: uuid.UUID | str) -> AsyncIterator[dict[str, Any]]:
    """Async generator yielding parsed events published to this user.

    Used by the WebSocket route; the subscription is cleaned up when the
    generator is closed (client disconnect cancels the consuming task).
    """
    client = get_redis()
    pubsub = client.pubsub()
    channel = _channel(user_id)
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                yield orjson.loads(message["data"])
            except orjson.JSONDecodeError:
                logger.warning("Dropping malformed pubsub payload on %s", channel)
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except (RedisError, OSError):  # pragma: no cover - best-effort cleanup
            pass
