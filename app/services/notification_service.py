"""In-app notifications: listing, read state, and creation + push."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.domain.enums import NotificationKind, NotificationSeverity
from app.infrastructure.db.models import Notification
from app.infrastructure.redis.pubsub import publish_event
from app.repositories import notification_repo
from app.schemas.notification import NotificationOut


async def list_notifications(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    unread_only: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Notification], int]:
    return await notification_repo.list_page(
        session, user_id, unread_only=unread_only, page=page, page_size=page_size
    )


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    return await notification_repo.unread_count(session, user_id)


async def mark_read(session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
    notification = await notification_repo.get_for_user(session, user_id, notification_id)
    if notification is None:
        raise not_found("Notification", notification_id)
    return await notification_repo.mark_read(session, notification)


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    return await notification_repo.mark_all_read(session, user_id)


async def create(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    kind: NotificationKind,
    severity: NotificationSeverity,
    title: dict[str, str],
    body: dict[str, str],
) -> Notification:
    """Persist a notification and push it over the user's realtime channel."""
    notification = await notification_repo.create(
        session,
        user_id=user_id,
        kind=kind.value,
        severity=severity.value,
        title=title,
        body=body,
    )
    payload = NotificationOut.model_validate(notification).model_dump(mode="json", by_alias=True)
    await publish_event(user_id, "notification.created", payload)
    return notification
