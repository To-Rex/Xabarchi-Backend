"""Gateway devices data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Device


def _live(user_id: uuid.UUID) -> list[Any]:
    return [Device.user_id == user_id, Device.deleted_at.is_(None)]


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[Device]:
    stmt = select(Device).where(*_live(user_id)).order_by(Device.created_at)
    return list((await session.scalars(stmt)).all())


async def count_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Device).where(*_live(user_id))
    return int(await session.scalar(stmt) or 0)


async def get_for_user(session: AsyncSession, user_id: uuid.UUID, device_id: uuid.UUID) -> Device | None:
    stmt = select(Device).where(Device.id == device_id, *_live(user_id))
    return await session.scalar(stmt)


async def get_by_token_hash(session: AsyncSession, token_hash: str) -> Device | None:
    stmt = select(Device).where(
        Device.token_hash == token_hash,
        Device.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create(session: AsyncSession, **fields: Any) -> Device:
    device = Device(**fields)
    session.add(device)
    await session.flush()
    return device


async def update_fields(session: AsyncSession, device: Device, fields: dict[str, Any]) -> Device:
    for name, value in fields.items():
        setattr(device, name, value)
    await session.flush()
    return device


async def soft_delete(session: AsyncSession, device: Device) -> None:
    device.deleted_at = datetime.now(UTC)
    # Free the token hash so a re-enrolled phone can never collide on the
    # unique index, and make sure the dead token stops authenticating.
    device.token_hash = None
    await session.flush()


async def set_default(session: AsyncSession, user_id: uuid.UUID, device: Device) -> Device:
    await session.execute(
        update(Device)
        .where(Device.user_id == user_id, Device.deleted_at.is_(None))
        .values(is_default=False)
    )
    device.is_default = True
    await session.flush()
    return device
