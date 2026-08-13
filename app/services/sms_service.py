"""SMS sending: validation, segmentation, quota, queueing, gateway protocol."""

from __future__ import annotations

import math
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, QuotaError, not_found
from app.domain.enums import PRIORITY_RANK, MessageStatus
from app.infrastructure.db.models import Device, Message, User
from app.infrastructure.redis.pubsub import publish_event
from app.infrastructure.redis.rate_limit import check_rate_limit
from app.repositories import billing_repo, contact_repo, device_repo, message_repo, user_repo
from app.repositories.message_repo import EnqueueItem
from app.schemas.message import GatewayReportIn, MessageOut, SendIn

SEND_RATE_LIMIT = 30  # requests
SEND_RATE_WINDOW_SECONDS = 60

# GSM 03.38 basic character set (+ LF/CR); extension chars cost 2 septets.
_GSM_BASIC = set(
    "@£$¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà\n\r"
)
_GSM_EXTENSION = set("^{}\\[~]|€")

_PHONE_RE = re.compile(r"^998\d{9}$")


def normalize_phone(raw: str) -> str:
    """Normalize any input form to ``998XXXXXXXXX`` or raise ``invalid_phone``.

    Accepts ``+998 90 123-45-67``, ``901234567`` (local 9 digits), etc.
    """
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 9:
        digits = "998" + digits
    if not _PHONE_RE.fullmatch(digits):
        raise AppError(f"Invalid phone number: {raw!r}", code="invalid_phone", status=422)
    return digits


def sms_segments(text: str) -> int:
    """Segment count: GSM-7 160/153 per part, UCS-2 70/67 (multipart headers)."""
    if all(ch in _GSM_BASIC or ch in _GSM_EXTENSION for ch in text):
        length = sum(2 if ch in _GSM_EXTENSION else 1 for ch in text)
        per_segment = 160 if length <= 160 else 153
    else:
        length = len(text)
        per_segment = 70 if length <= 70 else 67
    return max(1, math.ceil(length / per_segment))


# ---------------------------------------------------------------- sending


async def send(session: AsyncSession, user: User, data: SendIn) -> list[Message]:
    """Validate, meter, and enqueue one text to N recipients."""
    await check_rate_limit(
        f"sms:send:{user.id}", SEND_RATE_LIMIT, SEND_RATE_WINDOW_SECONDS
    )

    phones = [normalize_phone(raw) for raw in data.to]
    # Dedupe while preserving order — double recipients waste quota silently.
    phones = list(dict.fromkeys(phones))

    plan = await billing_repo.get_plan(session, user.plan_id)
    if plan is not None and user.sms_sent_this_month + len(phones) > plan.sms_per_month:
        raise QuotaError(
            f"Monthly SMS quota exceeded ({plan.sms_per_month} on plan '{user.plan_id}')"
        )

    device_id: uuid.UUID | None = data.device_id
    if device_id is not None:
        device = await device_repo.get_for_user(session, user.id, device_id)
        if device is None:
            raise not_found("Device", device_id)

    segments = sms_segments(data.text)
    contact_by_phone = await contact_repo.find_by_phones(session, user.id, phones)
    items: list[EnqueueItem] = [
        EnqueueItem(
            to_phone=phone,
            text_=data.text,
            segments=segments,
            priority=PRIORITY_RANK[data.priority],
            device_id=device_id,
            contact_id=contact_by_phone.get(phone),
        )
        for phone in phones
    ]
    messages = await message_repo.enqueue_many(session, user.id, items)
    await user_repo.increment_sms_sent(session, user, len(messages))

    for message in messages:
        await publish_event(user.id, "message.created", _message_payload(message))
    return messages


async def list_messages(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> tuple[list[Message], int, dict[str, int]]:
    items, total = await message_repo.list_page(
        session, user_id, status=status, search=search, page=page, page_size=page_size
    )
    counts = await message_repo.counts_by_status(session, user_id, search=search)
    return items, total, counts


async def get_message(session: AsyncSession, user_id: uuid.UUID, message_id: int) -> Message:
    message = await message_repo.get_for_user(session, user_id, message_id)
    if message is None:
        raise not_found("Message", message_id)
    return message


# ---------------------------------------------------------------- gateway


async def gateway_claim(session: AsyncSession, device: Device, limit: int) -> list[Message]:
    """Lease a batch of queued messages to this device (at-least-once)."""
    messages = await message_repo.claim_batch(
        session,
        device_id=device.id,
        user_id=device.user_id,
        limit=min(limit, settings.gateway_claim_max),
        lease_seconds=settings.gateway_lease_seconds,
    )
    for message in messages:
        await publish_event(device.user_id, "message.updated", _message_payload(message))
    return messages


async def gateway_ack(session: AsyncSession, device: Device, ids: list[int]) -> list[Message]:
    """Device confirms SIM handover; bumps the device's sent-today counter."""
    messages = await message_repo.ack_sent(session, device.user_id, ids)
    if messages:
        device.sent_today = device.sent_today + len(messages)
        await session.flush()
    for message in messages:
        await publish_event(device.user_id, "message.updated", _message_payload(message))
    return messages


async def gateway_report(session: AsyncSession, device: Device, data: GatewayReportIn) -> Message:
    """Final delivery report for one message."""
    message = await message_repo.report(
        session,
        device.user_id,
        data.id,
        MessageStatus(data.status).value,
        fail_reason=data.fail_reason.value if data.fail_reason else None,
    )
    if message is None:
        raise not_found("Message", data.id)
    await publish_event(device.user_id, "message.updated", _message_payload(message))
    return message


def _message_payload(message: Message) -> dict[str, object]:
    return MessageOut.model_validate(message).model_dump(mode="json", by_alias=True)
