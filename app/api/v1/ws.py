"""Realtime WebSocket: relays the user's Redis pub/sub channel to the browser.

Connect with ``ws(s)://host/api/v1/ws?token=<access JWT>``. Frames are the
exact payloads published by the services (``{"type": "notification",
"event": ..., "data": ...}``) plus a ``{"type": "ping"}`` heartbeat every
30 seconds so idle proxies keep the socket open.
"""

from __future__ import annotations

import asyncio
import logging

import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.exceptions import AuthError
from app.core.security import decode_token
from app.infrastructure.redis.pubsub import subscribe_user

logger = logging.getLogger(__name__)

router = APIRouter()

_PING_INTERVAL_SECONDS = 30.0
_PING_FRAME = orjson.dumps({"type": "ping"}).decode("utf-8")


@router.websocket("/ws")
async def websocket_events(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, "access")
    except AuthError:
        # 4401: policy-violation-style close mirroring HTTP 401.
        await websocket.close(code=4401, reason="Invalid or expired token")
        return
    user_id = str(payload["sub"])

    await websocket.accept()

    async def relay() -> None:
        async for event in subscribe_user(user_id):
            await websocket.send_text(orjson.dumps(event).decode("utf-8"))

    async def ping() -> None:
        while True:
            await asyncio.sleep(_PING_INTERVAL_SECONDS)
            await websocket.send_text(_PING_FRAME)

    async def reader() -> None:
        # We never act on client frames; this exists to surface disconnects.
        while True:
            await websocket.receive_text()

    tasks = [
        asyncio.create_task(relay(), name=f"ws-relay:{user_id}"),
        asyncio.create_task(ping(), name=f"ws-ping:{user_id}"),
        asyncio.create_task(reader(), name=f"ws-reader:{user_id}"),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("WebSocket task %s failed: %s", task.get_name(), exc)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await websocket.close()
        except RuntimeError:
            pass  # already closed by the client
