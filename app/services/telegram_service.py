"""Telegram bot integration: connect, subscribers, real broadcasts.

On connect the BotFather token is validated for real (``getMe``), the bot's
webhook is pointed at this API, and the token is stored *encrypted* (Fernet) so
broadcasts can replay it against ``sendMessage``. Subscribers arrive through the
webhook (anyone who messages the bot); broadcasts fan out to every subscriber we
hold a ``chat_id`` for.

Legacy/demo bots connected before real sending (no ``token_enc``) keep the old
mocked-delivery behavior so seeded demo data still looks alive.
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.core.exceptions import AppError, NotFoundError
from app.core.security import hash_token
from app.domain.enums import BroadcastStatus
from app.infrastructure.db.models import TelegramBot, User
from app.infrastructure.redis.pubsub import publish_event
from app.repositories import telegram_repo
from app.services import telegram_api
from app.services.telegram_api import TelegramError
from app.schemas.telegram import BotConnectIn, BotOut, BroadcastIn, BroadcastOut, SubscriberOut

logger = logging.getLogger(__name__)

_BOT_TOKEN_RE = re.compile(r"^\d{8,10}:[A-Za-z0-9_-]{30,}$")
_MOCK_DELIVERY_RATE = 0.97
# Telegram tolerates ~30 messages/second to different users; keep well under it.
_SEND_CONCURRENCY = 20


def _webhook_url(secret: str) -> str:
    return f"{settings.public_api_url}/api/v1/telegram/webhook/{secret}"


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

    # Validate the token for real and read the bot's identity from Telegram.
    try:
        me = await telegram_api.get_me(token)
    except TelegramError as exc:
        logger.info("Telegram getMe rejected a token: %s", exc.description)
        raise AppError(
            "Telegram rejected this token", code="invalid_bot_token", status=422
        ) from exc

    username = me.get("username") or _fallback_username(user.company)
    title = me.get("first_name") or user.company
    webhook_secret = secrets.token_urlsafe(24)

    # Subscribe to updates. Telegram requires a public HTTPS URL, so a local
    # (http://localhost) API can connect but won't receive subscribers.
    webhook_ok = False
    if settings.public_api_url.startswith("https://"):
        try:
            await telegram_api.set_webhook(token, _webhook_url(webhook_secret), webhook_secret)
            webhook_ok = True
        except TelegramError as exc:
            logger.warning("setWebhook failed for @%s: %s", username, exc.description)

    bot = await telegram_repo.create_bot(
        session,
        user_id=user.id,
        username=username,
        title=title,
        token_hash=hash_token(token),
        token_enc=encrypt_secret(token),
        bot_user_id=me.get("id"),
        webhook_secret=webhook_secret,
        webhook_ok=webhook_ok,
    )
    return await _to_bot_out(session, bot)


async def disconnect(session: AsyncSession, user_id: uuid.UUID) -> None:
    bot = await telegram_repo.get_bot(session, user_id)
    if bot is None:
        raise NotFoundError("No Telegram bot is connected")
    token = decrypt_secret(bot.token_enc) if bot.token_enc else None
    if token:
        try:
            await telegram_api.delete_webhook(token)
        except TelegramError as exc:
            logger.warning("deleteWebhook failed on disconnect: %s", exc.description)
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
    """Fan a broadcast out to every subscriber and record what was delivered."""
    bot = await _require_bot(session, user_id)

    # Legacy/demo bots (no encrypted token) keep the original mocked behavior.
    if not bot.token_enc:
        return await _create_mock_broadcast(session, user_id, bot, data)

    token = decrypt_secret(bot.token_enc)
    if token is None:
        raise AppError(
            "Bot token can't be read — please reconnect the bot",
            code="bot_token_unreadable",
            status=409,
        )

    subscribers = await telegram_repo.list_deliverable_subscribers(session, bot.id)
    audience = len(subscribers)
    broadcast = await telegram_repo.create_broadcast(
        session,
        bot_id=bot.id,
        kind=data.kind.value,
        text_=data.text,
        media_name=data.media_name,
        button_label=data.button_label,
        button_url=data.button_url,
        audience=audience,
        delivered=0,
        status=BroadcastStatus.sending.value,
    )

    delivered = await _fan_out(token, subscribers, data)

    status = (
        BroadcastStatus.failed.value
        if audience > 0 and delivered == 0
        else BroadcastStatus.sent.value
    )
    await telegram_repo.update_broadcast(
        session, broadcast, delivered=delivered, status=status
    )

    out = BroadcastOut.model_validate(broadcast)
    await publish_event(
        user_id, "telegram.broadcast", out.model_dump(mode="json", by_alias=True)
    )
    return out


async def _fan_out(token: str, subscribers: list, data: BroadcastIn) -> int:
    """Send to every subscriber concurrently; return the delivered count.

    We only have message text (and, for posts, an inline button) — media files
    aren't uploaded to us, so every kind goes out as a text message carrying the
    text/caption. Per-recipient failures (blocked bot, deleted account) are
    counted as undelivered, never fatal.
    """
    semaphore = asyncio.Semaphore(_SEND_CONCURRENCY)

    async def _one(chat_id: int) -> bool:
        async with semaphore:
            try:
                await telegram_api.send_message(
                    token,
                    chat_id,
                    data.text,
                    button_label=data.button_label,
                    button_url=data.button_url,
                )
                return True
            except TelegramError as exc:
                logger.info("Broadcast to chat %s failed: %s", chat_id, exc.description)
                return False

    results = await asyncio.gather(
        *(_one(sub.chat_id) for sub in subscribers if sub.chat_id is not None)
    )
    return sum(1 for ok in results if ok)


async def _create_mock_broadcast(
    session: AsyncSession, user_id: uuid.UUID, bot: TelegramBot, data: BroadcastIn
) -> BroadcastOut:
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


async def handle_update(session: AsyncSession, secret: str, update: dict) -> None:
    """Process a Telegram webhook update: register/refresh a subscriber.

    Anyone who sends the bot a message (typically ``/start``) becomes a
    subscriber. We ignore non-private chats and updates we can't attribute.
    """
    bot = await telegram_repo.get_bot_by_webhook_secret(session, secret)
    if bot is None:
        return

    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return
    chat = message.get("chat")
    if not isinstance(chat, dict) or chat.get("type") != "private":
        return

    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return

    name = " ".join(
        part for part in (chat.get("first_name"), chat.get("last_name")) if part
    ).strip() or (chat.get("username") or "Telegram user")
    username = chat.get("username")

    existing = await telegram_repo.get_subscriber_by_chat(session, bot.id, chat_id)
    if existing is not None:
        existing.name = name[:128]
        existing.username = username
        return

    await telegram_repo.create_subscriber(
        session,
        bot_id=bot.id,
        chat_id=chat_id,
        name=name[:128],
        username=username,
        avatar_hue=abs(chat_id) % 360,
        source="link",
    )
    await publish_event(bot.user_id, "telegram.subscriber", {"botId": str(bot.id)})


def _fallback_username(company: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return f"{slug or 'xabarchi'}_bot"


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
