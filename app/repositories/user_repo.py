"""Users data access."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
    return await session.scalar(stmt)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(
        func.lower(User.email) == email.strip().lower(),
        User.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create(session: AsyncSession, **fields: Any) -> User:
    user = User(**fields)
    session.add(user)
    await session.flush()
    return user


async def update(session: AsyncSession, user: User, fields: dict[str, Any]) -> User:
    for name, value in fields.items():
        setattr(user, name, value)
    await session.flush()
    return user


async def increment_sms_sent(session: AsyncSession, user: User, count: int) -> None:
    user.sms_sent_this_month = user.sms_sent_this_month + count
    await session.flush()
