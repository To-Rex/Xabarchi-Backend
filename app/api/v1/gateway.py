"""Gateway routes — the Android app's device-token-authenticated protocol.

Walkthrough: the device polls ``POST /gateway/claim`` for a leased batch,
sends each SMS over the SIM, confirms handover with ``POST /gateway/ack``,
and files final delivery reports with ``POST /gateway/report``. Heartbeats
keep the device marked online. Unacked leases expire back into the queue.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import DbSession, GatewayDevice
from app.schemas.common import CamelModel
from app.schemas.device import DeviceOut, HeartbeatIn
from app.schemas.message import GatewayAckIn, GatewayClaimIn, GatewayMessageOut, GatewayReportIn, MessageOut
from app.services import device_service, sms_service

router = APIRouter(prefix="/gateway", tags=["gateway"])


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
