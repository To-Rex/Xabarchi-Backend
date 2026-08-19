"""Messages ledger data access — enqueue, list, and the gateway queue.

The queue statements are the heart of the system:

- :func:`claim_batch` hands a device a lease on a batch of queued messages in
  ONE statement, using ``FOR UPDATE SKIP LOCKED`` so any number of devices can
  claim concurrently without ever double-sending.
- :func:`requeue_expired_leases` is the reaper: leases that were never acked
  go back to ``queued`` (or ``failed`` after max_attempts).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import case, delete, func, or_, select, text, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import FailReason, MessageStatus
from app.infrastructure.db.models import Message

# Messages that haven't gone to a device yet can still be canceled.
_CANCELABLE = [MessageStatus.queued.value, MessageStatus.scheduled.value]


class EnqueueItem(TypedDict, total=False):
    """One row for :func:`enqueue_many` (`text_` maps SQL column "text")."""

    to_phone: str
    text_: str
    segments: int
    priority: int
    device_id: uuid.UUID | None
    contact_id: uuid.UUID | None
    scheduled_at: datetime | None


# ----------------------------------------------------------------- enqueue


async def enqueue_many(
    session: AsyncSession,
    user_id: uuid.UUID,
    items: list[EnqueueItem],
    status: str = MessageStatus.queued.value,
) -> list[Message]:
    """Bulk-insert messages (``queued`` or ``scheduled``) and return the rows."""
    messages = [Message(user_id=user_id, status=status, **item) for item in items]
    session.add_all(messages)
    await session.flush()
    return messages


async def promote_due_scheduled(session: AsyncSession) -> int:
    """Move scheduled messages whose time has come into the live queue."""
    stmt = (
        update(Message)
        .where(
            Message.status == MessageStatus.scheduled.value,
            Message.scheduled_at.is_not(None),
            Message.scheduled_at <= func.now(),
        )
        .values(status=MessageStatus.queued.value)
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


# ------------------------------------------------------------------ listing


def _search_condition(search: str) -> Any:
    term = f"%{search.strip()}%"
    digits = "".join(ch for ch in search if ch.isdigit())
    conditions = [Message.text_.ilike(term)]
    if digits:
        conditions.append(Message.to_phone.like(f"%{digits}%"))
    return or_(*conditions)


async def list_page(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 12,
) -> tuple[list[Message], int]:
    conditions: list[Any] = [Message.user_id == user_id]
    if search:
        conditions.append(_search_condition(search))
    if status and status != "all":
        conditions.append(Message.status == status)

    total = int(
        await session.scalar(select(func.count()).select_from(Message).where(*conditions)) or 0
    )
    stmt = (
        select(Message)
        .where(*conditions)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await session.scalars(stmt)).all())
    return items, total


async def get_for_user(session: AsyncSession, user_id: uuid.UUID, message_id: int) -> Message | None:
    stmt = select(Message).where(Message.id == message_id, Message.user_id == user_id)
    return await session.scalar(stmt)


async def counts_by_status(
    session: AsyncSession, user_id: uuid.UUID, *, search: str | None = None
) -> dict[str, int]:
    """Per-status counts (plus ``all``) in a single GROUP BY query."""
    conditions: list[Any] = [Message.user_id == user_id]
    if search:
        conditions.append(_search_condition(search))
    stmt = select(Message.status, func.count()).where(*conditions).group_by(Message.status)
    counts = {status.value: 0 for status in MessageStatus}
    for status_value, count in (await session.execute(stmt)).all():
        counts[status_value] = int(count)
    counts["all"] = sum(counts.values())
    return counts


# -------------------------------------------------------------- gateway ops


async def claim_batch(
    session: AsyncSession,
    *,
    device_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int,
    lease_seconds: int,
) -> list[Message]:
    """Atomically lease up to ``limit`` queued messages to one device.

    Single statement: the subquery picks the oldest highest-priority queued
    rows addressed to this device (or unassigned) with ``FOR UPDATE SKIP
    LOCKED``, so concurrent devices skip each other's rows instead of
    blocking or double-claiming. The composite ``(id, created_at)`` key is
    required because the table is partitioned by ``created_at``.
    """
    picked = (
        select(Message.id, Message.created_at)
        .where(
            Message.user_id == user_id,
            or_(Message.device_id == device_id, Message.device_id.is_(None)),
            Message.status == MessageStatus.queued.value,
        )
        .order_by(Message.priority, Message.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    stmt = (
        update(Message)
        .where(tuple_(Message.id, Message.created_at).in_(picked))
        .values(
            status=MessageStatus.sending.value,
            device_id=device_id,
            lease_expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds),
            attempts=Message.attempts + 1,
        )
        .returning(Message)
        .execution_options(synchronize_session=False)
    )
    rows = list((await session.scalars(stmt)).all())
    rows.sort(key=lambda message: (message.priority, message.created_at))
    return rows


async def ack_sent(session: AsyncSession, user_id: uuid.UUID, ids: list[int]) -> list[Message]:
    """Device confirms handover to the SIM: sending -> sent."""
    if not ids:
        return []
    stmt = (
        update(Message)
        .where(
            Message.user_id == user_id,
            Message.id.in_(ids),
            Message.status == MessageStatus.sending.value,
        )
        .values(
            status=MessageStatus.sent.value,
            sent_at=func.now(),
            lease_expires_at=None,
        )
        .returning(Message)
        .execution_options(synchronize_session=False)
    )
    return list((await session.scalars(stmt)).all())


async def report(
    session: AsyncSession,
    user_id: uuid.UUID,
    message_id: int,
    status: str,
    fail_reason: str | None = None,
) -> Message | None:
    """Final delivery report: ``delivered`` or ``failed``."""
    values: dict[str, Any] = {"status": status, "lease_expires_at": None}
    if status == MessageStatus.delivered.value:
        values["delivered_at"] = func.now()
        values["fail_reason"] = None
    else:
        values["fail_reason"] = fail_reason or FailReason.no_signal.value
    stmt = (
        update(Message)
        .where(Message.user_id == user_id, Message.id == message_id)
        .values(**values)
        .returning(Message)
        .execution_options(synchronize_session=False)
    )
    return await session.scalar(stmt)


async def cancel(session: AsyncSession, user_id: uuid.UUID, message_id: int) -> Message | None:
    """Cancel a still-queued message: queued -> canceled.

    Atomic ``WHERE status IN (queued, scheduled)`` so a message already claimed
    by a device (``sending``) or finished can't be canceled — returns None in
    that case (or if it isn't the user's).
    """
    stmt = (
        update(Message)
        .where(
            Message.user_id == user_id,
            Message.id == message_id,
            Message.status.in_(_CANCELABLE),
        )
        .values(status=MessageStatus.canceled.value, lease_expires_at=None)
        .returning(Message)
        .execution_options(synchronize_session=False)
    )
    return await session.scalar(stmt)


async def bulk_cancel(session: AsyncSession, user_id: uuid.UUID, ids: list[int]) -> int:
    """Cancel every still-queued message among ``ids``; returns how many changed."""
    if not ids:
        return 0
    stmt = (
        update(Message)
        .where(
            Message.user_id == user_id,
            Message.id.in_(ids),
            Message.status.in_(_CANCELABLE),
        )
        .values(status=MessageStatus.canceled.value, lease_expires_at=None)
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


async def bulk_set_priority(
    session: AsyncSession, user_id: uuid.UUID, ids: list[int], rank: int
) -> int:
    """Re-prioritize still-queued messages among ``ids`` (only queued can move)."""
    if not ids:
        return 0
    stmt = (
        update(Message)
        .where(
            Message.user_id == user_id,
            Message.id.in_(ids),
            Message.status == MessageStatus.queued.value,
        )
        .values(priority=rank)
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


async def bulk_delete(session: AsyncSession, user_id: uuid.UUID, ids: list[int]) -> int:
    """Permanently delete the given messages; returns how many were removed."""
    if not ids:
        return 0
    stmt = (
        delete(Message)
        .where(Message.user_id == user_id, Message.id.in_(ids))
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


async def delete_all(
    session: AsyncSession, user_id: uuid.UUID, status: str | None = None
) -> int:
    """Wipe all of a user's messages (optionally only one status). Returns count."""
    conditions = [Message.user_id == user_id]
    if status:
        conditions.append(Message.status == status)
    stmt = (
        delete(Message)
        .where(*conditions)
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    return len((await session.scalars(stmt)).all())


async def requeue_expired_leases(session: AsyncSession) -> int:
    """Reaper: return dead-device leases to the queue (or fail them out).

    A message stuck in ``sending`` past its lease either goes back to
    ``queued`` for another attempt, or — once ``attempts`` reaches
    ``max_attempts`` — is failed with ``device_offline``.
    """
    stmt = (
        update(Message)
        .where(
            Message.status == MessageStatus.sending.value,
            Message.lease_expires_at.is_not(None),
            Message.lease_expires_at < func.now(),
        )
        .values(
            status=case(
                (Message.attempts >= Message.max_attempts, MessageStatus.failed.value),
                else_=MessageStatus.queued.value,
            ),
            fail_reason=case(
                (Message.attempts >= Message.max_attempts, FailReason.device_offline.value),
                else_=None,
            ),
            lease_expires_at=None,
        )
        .returning(Message.id)
        .execution_options(synchronize_session=False)
    )
    result = await session.execute(stmt)
    return len(result.all())


# ---------------------------------------------------------------- analytics


async def overview_counts(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """One aggregate pass over the ledger for the dashboard overview."""
    stmt = text(
        """
        SELECT
            count(*) FILTER (
                WHERE created_at >= date_trunc('day', now())
                  AND status IN ('sent', 'delivered')
            ) AS sent_today,
            count(*) FILTER (
                WHERE created_at >= date_trunc('day', now()) - interval '1 day'
                  AND created_at <  date_trunc('day', now())
                  AND status IN ('sent', 'delivered')
            ) AS sent_yesterday,
            count(*) FILTER (WHERE status IN ('queued', 'sending')) AS queued,
            count(*) FILTER (
                WHERE created_at >= now() - interval '30 days'
                  AND status = 'delivered'
            ) AS delivered_30d,
            count(*) FILTER (
                WHERE created_at >= now() - interval '30 days'
                  AND status IN ('sent', 'delivered')
            ) AS sent_30d
        FROM messages
        WHERE user_id = :user_id
        """
    )
    row = (await session.execute(stmt, {"user_id": user_id})).one()
    return {
        "sent_today": int(row.sent_today),
        "sent_yesterday": int(row.sent_yesterday),
        "queued": int(row.queued),
        "delivered_30d": int(row.delivered_30d),
        "sent_30d": int(row.sent_30d),
    }


async def daily_stats(
    session: AsyncSession, user_id: uuid.UUID, days: int = 30
) -> list[dict[str, Any]]:
    """Rows of the ``daily_stats`` view for the last ``days`` days."""
    stmt = text(
        """
        SELECT date, sent, delivered, failed
        FROM daily_stats
        WHERE user_id = :user_id
          AND date >= current_date - CAST(:days AS integer)
        ORDER BY date
        """
    )
    rows = (await session.execute(stmt, {"user_id": user_id, "days": days})).all()
    return [
        {
            "date": row.date,
            "sent": int(row.sent),
            "delivered": int(row.delivered),
            "failed": int(row.failed),
        }
        for row in rows
    ]


async def recent(session: AsyncSession, user_id: uuid.UUID, limit: int = 6) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.user_id == user_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())
