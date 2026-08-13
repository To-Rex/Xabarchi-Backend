"""Telegram bot integration: connect, subscribers, broadcasts.

The bot token is validated against BotFather's format, then only its SHA-256
hash is stored. Actual Telegram API calls are out of scope for the MVP:
broadcasts are recorded as sent with a mocked 97% delivery rate.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.core.security import hash_token
from app.domain.enums import BroadcastStatus
from app.infrastructure.db.models import BotBroadcast, TelegramBot, User
from app.infrastructure.redis.pubsub import publish_event
from app.repositories import telegram_repo
from app.schemas.telegram import BotConnectIn, BotOut, BroadcastIn, BroadcastOut, SubscriberOut

_BOT_TOKEN_RE = re.compile(r"^\d{8,10}:[A-Za-z0-9_-]{30,}$")
_MOCK_DELIVERY_RATE = 0.97


def _derive_username(company: str) -> str:
    """Fake @username from the company name until real getMe() wiring lands."""
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug or 'xabarchi'}_bot"


async def get_bot(session: AsyncSession, user_id: uuid.UUID) -> BotOut:
    bot = await telegram_repo.get_bot(session, user_id)
    if bot is None:
        raise NotFoundError("No Telegram bot is connected")
    return await _to_bot_out(session, bot)


async def connect(session: AsyncSession, user: User, data: BotConnectIn) -> BotOut:
    token = data.token.strip()
    if not _BOT_TOKEN_RE.fullmatch(token):
        raise AppError("Invalid bot token format", code="invalid_bot_token", status=422)
    existing = await telegram_repo.get_bot(session, user.id)
    if existing is not None:
        raise AppError("A bot is already connected", code="bot_exists", status=409)
    bot = await telegram_repo.create_bot(
        session,
        user_id=user.id,
        username=_derive_username(user.company),
        title=user.company,
        token_hash=hash_token(token),
    )
    return await _to_bot_out(session, bot)


async def disconnect(session: AsyncSession, user_id: uuid.UUID) -> None:
    bot = await telegram_repo.get_bot(session, user_id)
    if bot is None:
        raise NotFoundError("No Telegram bot is connected")
    await telegram_repo.soft_delete_bot(session, bot)


async def list_subscribers(
    session: AsyncSession, user_id: uuid.UUID, *, page: int = 1, page_size: int = 50
) -> tuple[list[SubscriberOut], int]:
    bot = await _require_bot(session, user_id)
    subscribers, total = await telegram_repo.list_subscribers(
        session, bot.id, page=page, page_size=page_size
    )
    return [SubscriberOut.model_validate(sub) for sub in subscribers], total


async def list_broadcasts(
    session: AsyncSession, user_id: uuid.UUID, *, page: int = 1, page_size: int = 20
) -> tuple[list[BroadcastOut], int]:
    bot = await _require_bot(session, user_id)
    broadcasts, total = await telegram_repo.list_broadcasts(
        session, bot.id, page=page, page_size=page_size
    )
    return [BroadcastOut.model_validate(b) for b in broadcasts], total


async def create_broadcast(
    session: AsyncSession, user_id: uuid.UUID, data: BroadcastIn
) -> BroadcastOut:
    """Record a broadcast to every subscriber.

    MVP behavior: created directly as ``sent`` with delivered mocked at 97%
    of the audience — the real Telegram sender worker replaces this later.
    """
    bot = await _require_bot(session, user_id)
    audience = await telegram_repo.subscriber_count(session, bot.id)
    broadcast = await telegram_repo.create_broadcast(
        session,
        bot_id=bot.id,
        kind=data.kind.value,
        text_=data.text,
        media_name=data.media_name,
        button_label=data.button_label,
        button_url=data.button_url,
        audience=audience,
        delivered=round(audience * _MOCK_DELIVERY_RATE),
        status=BroadcastStatus.sent.value,
    )
    out = BroadcastOut.model_validate(broadcast)
    await publish_event(
        user_id, "telegram.broadcast", out.model_dump(mode="json", by_alias=True)
    )
    return out


async def _require_bot(session: AsyncSession, user_id: uuid.UUID) -> TelegramBot:
    bot = await telegram_repo.get_bot(session, user_id)
    if bot is None:
        raise NotFoundError("No Telegram bot is connected")
    return bot


async def _to_bot_out(session: AsyncSession, bot: TelegramBot) -> BotOut:
    count = await telegram_repo.subscriber_count(session, bot.id)
    return BotOut(
        id=bot.id,
        username=bot.username,
        title=bot.title,
        status=bot.status,
        connected_at=bot.connected_at,
        subscriber_count=count,
        webhook_ok=bot.webhook_ok,
    )
