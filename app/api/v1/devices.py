"""Device routes: CRUD, pairing, default selection, and device heartbeat."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, GatewayDevice
from app.core.exceptions import forbidden
from app.schemas.device import (
    DeviceCreateIn,
    DeviceOut,
    DeviceUpdateIn,
    HeartbeatIn,
    PairCompleteIn,
    PairOut,
    PairStartOut,
)
from app.services import device_service

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(session: DbSession, user: CurrentUser) -> list[DeviceOut]:
    devices = await device_service.list_devices(session, user.id)
    return [DeviceOut.model_validate(d) for d in devices]


@router.post("/pair", response_model=PairOut, status_code=status.HTTP_201_CREATED)
async def pair_device(session: DbSession, user: CurrentUser, body: DeviceCreateIn) -> PairOut:
    device, token = await device_service.pair(session, user, body)
    return PairOut(device=DeviceOut.model_validate(device), token=token)


@router.post("/pair/start", response_model=PairStartOut)
async def pair_start(user: CurrentUser) -> PairStartOut:
    """Dashboard side of QR pairing: mint a short-lived code to render as QR."""
    code, ttl = await device_service.pair_start(user.id)
    return PairStartOut(code=code, qr_payload=f"xabarchi://pair?code={code}", expires_in=ttl)


@router.post("/pair/complete", response_model=PairOut, status_code=status.HTTP_201_CREATED)
async def pair_complete(session: DbSession, body: PairCompleteIn) -> PairOut:
    """Phone side of QR pairing — unauthenticated; the scanned code IS the auth."""
    device, token = await device_service.pair_complete(
        session, body.code, DeviceCreateIn(**body.model_dump(exclude={"code"}))
    )
    return PairOut(device=DeviceOut.model_validate(device), token=token)


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(session: DbSession, user: CurrentUser, device_id: uuid.UUID) -> DeviceOut:
    device = await device_service.get_device(session, user.id, device_id)
    return DeviceOut.model_validate(device)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(
    session: DbSession, user: CurrentUser, device_id: uuid.UUID, body: DeviceUpdateIn
) -> DeviceOut:
    device = await device_service.update_device(session, user.id, device_id, body)
    return DeviceOut.model_validate(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(session: DbSession, user: CurrentUser, device_id: uuid.UUID) -> None:
    await device_service.delete_device(session, user.id, device_id)


@router.post("/{device_id}/default", response_model=DeviceOut)
async def set_default_device(
    session: DbSession, user: CurrentUser, device_id: uuid.UUID
) -> DeviceOut:
    device = await device_service.set_default(session, user.id, device_id)
    return DeviceOut.model_validate(device)


@router.post("/{device_id}/heartbeat", response_model=DeviceOut)
async def device_heartbeat(
    session: DbSession, device: GatewayDevice, device_id: uuid.UUID, body: HeartbeatIn
) -> DeviceOut:
    """Heartbeat authenticated by the device's own X-Device-Token."""
    if device.id != device_id:
        raise forbidden("Device token does not match this device id")
    updated = await device_service.heartbeat(session, device, body)
    return DeviceOut.model_validate(updated)
