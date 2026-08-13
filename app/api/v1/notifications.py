"""In-app notification routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import CamelModel, Page
from app.schemas.notification import NotificationOut, UnreadCountOut
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


class MarkAllOut(CamelModel):
    marked: int


@router.get("", response_model=Page[NotificationOut])
async def list_notifications(
    session: DbSession,
    user: CurrentUser,
    unread_only: Annotated[bool, Query(alias="unreadOnly")] = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[NotificationOut]:
    items, total = await notification_service.list_notifications(
        session, user.id, unread_only=unread_only, page=page, page_size=page_size
    )
    return Page[NotificationOut](
        items=[NotificationOut.model_validate(n) for n in items],
        total=total,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(session: DbSession, user: CurrentUser) -> UnreadCountOut:
    return UnreadCountOut(unread=await notification_service.unread_count(session, user.id))


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    session: DbSession, user: CurrentUser, notification_id: uuid.UUID
) -> NotificationOut:
    notification = await notification_service.mark_read(session, user.id, notification_id)
    return NotificationOut.model_validate(notification)


@router.post("/read-all", response_model=MarkAllOut)
async def mark_all_read(session: DbSession, user: CurrentUser) -> MarkAllOut:
    return MarkAllOut(marked=await notification_service.mark_all_read(session, user.id))
