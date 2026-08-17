"""Admin-panel data access: platform-wide aggregates and cross-user listings."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Device, Invoice, Message, TelegramBot, User


async def overview(session: AsyncSession) -> dict[str, Any]:
    """Platform-wide snapshot for the admin dashboard."""

    async def scalar(stmt: Any) -> int:
        return int(await session.scalar(stmt) or 0)

    total_users = await scalar(
        select(func.count()).select_from(User).where(User.deleted_at.is_(None))
    )
    paid_users = await scalar(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.plan_id.in_(("biznes", "korxona")),
               User.plan_expires_at.is_not(None), User.plan_expires_at > func.now())
    )
    total_devices = await scalar(
        select(func.count()).select_from(Device).where(Device.deleted_at.is_(None))
    )
    online_devices = await scalar(
        select(func.count())
        .select_from(Device)
        .where(Device.deleted_at.is_(None), Device.status == "online")
    )
    messages_today = await scalar(
        select(func.count()).select_from(Message).where(
            Message.created_at >= func.date_trunc("day", func.now())
        )
    )
    messages_month = await scalar(
        select(func.count()).select_from(Message).where(
            Message.created_at >= func.date_trunc("month", func.now())
        )
    )
    delivered_month = await scalar(
        select(func.count()).select_from(Message).where(
            Message.created_at >= func.date_trunc("month", func.now()),
            Message.status == "delivered",
        )
    )
    total_bots = await scalar(
        select(func.count()).select_from(TelegramBot).where(TelegramBot.deleted_at.is_(None))
    )
    revenue_month = int(
        await session.scalar(
            select(func.coalesce(func.sum(Invoice.amount), 0)).where(
                Invoice.status == "paid",
                Invoice.date >= func.date_trunc("month", func.now()),
            )
        )
        or 0
    )

    plan_rows = await session.execute(
        select(User.plan_id, func.count())
        .where(User.deleted_at.is_(None))
        .group_by(User.plan_id)
    )
    plan_counts = {plan_id: int(count) for plan_id, count in plan_rows.all()}

    return {
        "total_users": total_users,
        "paid_users": paid_users,
        "total_devices": total_devices,
        "online_devices": online_devices,
        "messages_today": messages_today,
        "messages_month": messages_month,
        "delivered_month": delivered_month,
        "total_bots": total_bots,
        "revenue_month": revenue_month,
        "plan_counts": plan_counts,
    }


async def list_users(
    session: AsyncSession, *, search: str | None, page: int, page_size: int
) -> tuple[list[User], int]:
    conditions = [User.deleted_at.is_(None)]
    if search:
        like = f"%{search.strip()}%"
        conditions.append(
            or_(
                User.email.ilike(like),
                User.company.ilike(like),
                User.first_name.ilike(like),
                User.last_name.ilike(like),
                User.phone.ilike(like),
            )
        )
    total = int(
        await session.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    )
    stmt = (
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), total


async def device_counts(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not user_ids:
        return {}
    rows = await session.execute(
        select(Device.user_id, func.count())
        .where(Device.user_id.in_(user_ids), Device.deleted_at.is_(None))
        .group_by(Device.user_id)
    )
    return {user_id: int(count) for user_id, count in rows.all()}


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id))


async def list_devices(
    session: AsyncSession, *, page: int, page_size: int
) -> tuple[list[tuple[Device, str, str]], int]:
    """All devices with their owner's e-mail + company."""
    conditions = [Device.deleted_at.is_(None)]
    total = int(
        await session.scalar(select(func.count()).select_from(Device).where(*conditions)) or 0
    )
    stmt = (
        select(Device, User.email, User.company)
        .join(User, User.id == Device.user_id)
        .where(*conditions)
        .order_by(Device.last_seen_at.desc().nullslast(), Device.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], row[2]) for row in rows], total


async def list_invoices(
    session: AsyncSession, *, page: int, page_size: int
) -> tuple[list[tuple[Invoice, str, str]], int]:
    total = int(await session.scalar(select(func.count()).select_from(Invoice)) or 0)
    stmt = (
        select(Invoice, User.email, User.company)
        .join(User, User.id == Invoice.user_id)
        .order_by(Invoice.date.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return [(row[0], row[1], row[2]) for row in rows], total
