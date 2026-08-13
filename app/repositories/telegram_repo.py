"""Telegram bots, subscribers, and broadcasts data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import BotBroadcast, BotSubscriber, TelegramBot


async def get_bot(session: AsyncSession, user_id: uuid.UUID) -> TelegramBot | None:
    stmt = select(TelegramBot).where(
        TelegramBot.user_id == user_id,
        TelegramBot.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def get_bot_by_webhook_secret(session: AsyncSession, secret: str) -> TelegramBot | None:
    stmt = select(TelegramBot).where(
        TelegramBot.webhook_secret == secret,
        TelegramBot.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create_bot(session: AsyncSession, **fields: Any) -> TelegramBot:
    bot = TelegramBot(**fields)
    session.add(bot)
    await session.flush()
    return bot


async def soft_delete_bot(session: AsyncSession, bot: TelegramBot) -> None:
    bot.deleted_at = datetime.now(UTC)
    await session.flush()


async def subscriber_count(session: AsyncSession, bot_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(BotSubscriber)
        .where(BotSubscriber.bot_id == bot_id, BotSubscriber.deleted_at.is_(None))
    )
    return int(await session.scalar(stmt) or 0)


async def get_subscriber_by_chat(
    session: AsyncSession, bot_id: uuid.UUID, chat_id: int
) -> BotSubscriber | None:
    stmt = select(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id,
        BotSubscriber.chat_id == chat_id,
        BotSubscriber.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create_subscriber(session: AsyncSession, **fields: Any) -> BotSubscriber:
    subscriber = BotSubscriber(**fields)
    session.add(subscriber)
    await session.flush()
    return subscriber


async def list_deliverable_subscribers(
    session: AsyncSession, bot_id: uuid.UUID
) -> list[BotSubscriber]:
    """Every live subscriber we actually have a Telegram chat_id for."""
    stmt = select(BotSubscriber).where(
        BotSubscriber.bot_id == bot_id,
        BotSubscriber.chat_id.is_not(None),
        BotSubscriber.deleted_at.is_(None),
    )
    return list((await session.scalars(stmt)).all())


async def list_subscribers(
    session: AsyncSession, bot_id: uuid.UUID, *, page: int = 1, page_size: int = 50
) -> tuple[list[BotSubscriber], int]:
    conditions = [BotSubscriber.bot_id == bot_id, BotSubscriber.deleted_at.is_(None)]
    total = int(
        await session.scalar(select(func.count()).select_from(BotSubscriber).where(*conditions)) or 0
    )
    stmt = (
        select(BotSubscriber)
        .where(*conditions)
        .order_by(BotSubscriber.joined_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), total


async def list_broadcasts(
    session: AsyncSession, bot_id: uuid.UUID, *, page: int = 1, page_size: int = 20
) -> tuple[list[BotBroadcast], int]:
    total = int(
        await session.scalar(
            select(func.count()).select_from(BotBroadcast).where(BotBroadcast.bot_id == bot_id)
        )
        or 0
    )
    stmt = (
        select(BotBroadcast)
        .where(BotBroadcast.bot_id == bot_id)
        .order_by(BotBroadcast.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list((await session.scalars(stmt)).all()), total


async def create_broadcast(session: AsyncSession, **fields: Any) -> BotBroadcast:
    broadcast = BotBroadcast(**fields)
    session.add(broadcast)
    await session.flush()
    return broadcast


async def update_broadcast(
    session: AsyncSession, broadcast: BotBroadcast, **fields: Any
) -> BotBroadcast:
    for key, value in fields.items():
        setattr(broadcast, key, value)
    await session.flush()
    return broadcast
