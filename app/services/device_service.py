"""Gateway-device lifecycle: pairing (direct + QR), CRUD, heartbeats."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, QuotaError, not_found
from app.core.security import generate_device_token
from app.domain.enums import DeviceConnection, DeviceStatus
from app.infrastructure.db.models import Device, User
from app.infrastructure.redis.client import get_redis
from app.infrastructure.redis.pubsub import publish_event
from app.repositories import billing_repo, device_repo, user_repo
from app.schemas.device import DeviceCreateIn, DeviceOut, DeviceUpdateIn, HeartbeatIn
from app.services import subscription_service

# QR pairing codes live briefly in Redis: pair:{code} -> user_id.
PAIR_CODE_TTL_SECONDS = 120
_PAIR_KEY = "pair:{code}"


async def list_devices(session: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    return await device_repo.list_for_user(session, user_id)


async def get_device(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> Device:
    device = await device_repo.get_for_user(session, user_id, device_id)
    if device is None:
        raise not_found("Device", device_id)
    return device


async def pair(session: AsyncSession, user: User, data: DeviceCreateIn) -> tuple[Device, str]:
    """Enroll a new phone: enforce the plan cap, mint the one-time token.

    Returns the device and the FULL token — the only moment it ever exists in
    plaintext; only its hash is stored.
    """
    subscription_service.assert_active(user)
    plan = await billing_repo.get_plan(session, user.plan_id)
    device_count = await device_repo.count_for_user(session, user.id)
    if plan is not None and device_count >= plan.max_devices:
        raise QuotaError(
            f"Plan '{user.plan_id}' allows at most {plan.max_devices} device(s)"
        )
    token, token_hash = generate_device_token()
    device = await device_repo.create(
        session,
        user_id=user.id,
        name=data.name,
        model=data.model,
        phone=data.phone,
        operator=data.operator.value,
        android_version=data.android_version,
        app_version=data.app_version,
        daily_limit=data.daily_limit,
        token_hash=token_hash,
        is_default=device_count == 0,  # first device becomes the default
    )
    await publish_event(user.id, "device.created", _device_payload(device))
    return device, token


async def pair_start(user: User) -> tuple[str, int]:
    """Mint a one-time pairing code for the QR the dashboard displays.

    The code maps to the user in Redis with a short TTL; scanning phones
    exchange it for a permanent device token via ``pair_complete``. Gated so a
    lapsed account can't even render a QR to pair from.
    """
    subscription_service.assert_active(user)
    code = secrets.token_urlsafe(24)
    await get_redis().set(
        _PAIR_KEY.format(code=code), str(user.id), ex=PAIR_CODE_TTL_SECONDS
    )
    return code, PAIR_CODE_TTL_SECONDS


async def pair_complete(
    session: AsyncSession, code: str, data: DeviceCreateIn
) -> tuple[Device, str]:
    """Phone-side half of QR pairing: swap the scanned code for a device token.

    GETDEL makes the code strictly one-time even under concurrent attempts.
    Runs unauthenticated, so failures stay deliberately vague.
    """
    user_id_raw = await get_redis().getdel(_PAIR_KEY.format(code=code))
    if not user_id_raw:
        raise AuthError("Pairing code is invalid or expired")
    user = await user_repo.get_by_id(session, uuid.UUID(user_id_raw))
    if user is None or user.deleted_at is not None:
        raise AuthError("Pairing code is invalid or expired")
    device, token = await pair(session, user, data)  # enforces the plan cap
    await publish_event(user.id, "device.paired", _device_payload(device))
    return device, token


async def update_device(
    session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID, data: DeviceUpdateIn
) -> Device:
    device = await get_device(session, user_id, device_id)
    fields = data.model_dump(exclude_none=True)
    if "operator" in fields:
        fields["operator"] = data.operator.value if data.operator else device.operator
    device = await device_repo.update_fields(session, device, fields)
    await publish_event(user_id, "device.updated", _device_payload(device))
    return device


async def delete_device(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> None:
    device = await get_device(session, user_id, device_id)
    await device_repo.soft_delete(session, device)
    await publish_event(user_id, "device.deleted", {"id": str(device_id)})


async def set_default(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> Device:
    device = await get_device(session, user_id, device_id)
    device = await device_repo.set_default(session, user_id, device)
    await publish_event(user_id, "device.updated", _device_payload(device))
    return device


async def heartbeat(session: AsyncSession, device: Device, data: HeartbeatIn) -> Device:
    """Device check-in: refresh liveness/telemetry and broadcast the change."""
    device.status = DeviceStatus.online.value
    device.connection = (
        data.connection.value
        if data.connection != DeviceConnection.offline
        else DeviceConnection.polling.value
    )
    device.battery = data.battery
    device.signal = data.signal
    if data.sent_today is not None:
        device.sent_today = data.sent_today
    device.last_seen_at = datetime.now(UTC)
    await session.flush()
    await publish_event(device.user_id, "device.updated", _device_payload(device))
    return device


def _device_payload(device: Device) -> dict[str, object]:
    return DeviceOut.model_validate(device).model_dump(mode="json", by_alias=True)
