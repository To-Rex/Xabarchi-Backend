"""Gateway routes — the Android app's device-token-authenticated protocol.

Walkthrough: the device polls ``POST /gateway/claim`` for a leased batch,
sends each SMS over the SIM, confirms handover with ``POST /gateway/ack``,
and files final delivery reports with ``POST /gateway/report``. Heartbeats
keep the device marked online. Unacked leases expire back into the queue.
"""

from __future__ import annotations

import asyncio
import logging

import orjson
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.deps import DbSession, GatewayDevice
from app.core.security import hash_token
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.redis.pubsub import subscribe_user
from app.repositories import device_repo
from app.schemas.common import CamelModel
from app.schemas.device import DeviceOut, HeartbeatIn
from app.schemas.message import GatewayAckIn, GatewayClaimIn, GatewayMessageOut, GatewayReportIn, MessageOut
from app.services import device_service, sms_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gateway", tags=["gateway"])

_PING_INTERVAL_SECONDS = 30.0
_PING_FRAME = orjson.dumps({"type": "ping"}).decode("utf-8")


class AckOut(CamelModel):
    acked: int


@router.post("/claim", response_model=list[GatewayMessageOut])
async def claim(session: DbSession, device: GatewayDevice, body: GatewayClaimIn) -> list[GatewayMessageOut]:
    messages = await sms_service.gateway_claim(session, device, body.limit)
    return [GatewayMessageOut.model_validate(m) for m in messages]


@router.post("/ack", response_model=AckOut)
async def ack(session: DbSession, device: GatewayDevice, body: GatewayAckIn) -> AckOut:
    messages = await sms_service.gateway_ack(session, device, body.ids)
    return AckOut(acked=len(messages))


@router.post("/report", response_model=MessageOut)
async def report(session: DbSession, device: GatewayDevice, body: GatewayReportIn) -> MessageOut:
    message = await sms_service.gateway_report(session, device, body)
    return MessageOut.model_validate(message)


@router.post("/heartbeat", response_model=DeviceOut)
async def heartbeat(session: DbSession, device: GatewayDevice, body: HeartbeatIn) -> DeviceOut:
    updated = await device_service.heartbeat(session, device, body)
    return DeviceOut.model_validate(updated)


@router.websocket("/ws")
async def gateway_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    """Realtime nudge channel for the Android gateway.

    Connect with ``ws(s)://host/api/v1/gateway/ws?token=<device_token>``.
    Relays the owner's events (``message.created``/``message.updated``) so the
    device can claim instantly instead of waiting for the next poll. Auth is
    the device token itself (WebSockets can't send custom headers from the
    Android client, so it rides in the query string).
    """
    async with async_session_factory() as session:
        device = await device_repo.get_by_token_hash(session, hash_token(token.strip()))
    if device is None:
        await websocket.close(code=4401, reason="Invalid device token")
        return

    user_id = str(device.user_id)
    await websocket.accept()

    async def relay() -> None:
        async for event in subscribe_user(user_id):
            await websocket.send_text(orjson.dumps(event).decode("utf-8"))

    async def ping() -> None:
        while True:
            await asyncio.sleep(_PING_INTERVAL_SECONDS)
            await websocket.send_text(_PING_FRAME)

    async def reader() -> None:
        while True:
            await websocket.receive_text()

    tasks = [
        asyncio.create_task(relay(), name=f"gw-relay:{user_id}"),
        asyncio.create_task(ping(), name=f"gw-ping:{user_id}"),
        asyncio.create_task(reader(), name=f"gw-reader:{user_id}"),
    ]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                logger.warning("Gateway WS task %s failed: %s", task.get_name(), exc)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await websocket.close()
        except RuntimeError:
            pass
