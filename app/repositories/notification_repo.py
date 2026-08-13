"""In-app notifications data access."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Notification


async def list_page(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int]:
    conditions: list[Any] = [Notification.user_id == user_id]
    if unread_only:
        conditions.append(Notification.read.is_(False))
    total = int(
        await session.scalar(select(func.count()).select_from(Notification).where(*conditions)) or 0
    )
    stmt = (
        select(Notification)
        .where(*conditions)
        .order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), total


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read.is_(False))
    )
    return int(await session.scalar(stmt) or 0)


async def get_for_user(
    session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification | None:
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    )
    return await session.scalar(stmt)


async def mark_read(session: AsyncSession, notification: Notification) -> Notification:
    notification.read = True
    await session.flush()
    return notification


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read.is_(False))
        .values(read=True)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    return int(result.rowcount or 0)


async def create(session: AsyncSession, **fields: Any) -> Notification:
    notification = Notification(**fields)
    session.add(notification)
    await session.flush()
    return notification
