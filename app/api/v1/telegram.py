"""Telegram bot routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.telegram import BotConnectIn, BotOut, BroadcastIn, BroadcastOut, SubscriberOut
from app.services import telegram_service

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/bot", response_model=BotOut)
async def get_bot(session: DbSession, user: CurrentUser) -> BotOut:
    return await telegram_service.get_bot(session, user.id)


@router.post("/connect", response_model=BotOut, status_code=status.HTTP_201_CREATED)
async def connect_bot(session: DbSession, user: CurrentUser, body: BotConnectIn) -> BotOut:
    return await telegram_service.connect(session, user, body)


@router.delete("/bot", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_bot(session: DbSession, user: CurrentUser) -> None:
    await telegram_service.disconnect(session, user.id)


@router.get("/subscribers", response_model=Page[SubscriberOut])
async def list_subscribers(
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize")] = 50,
) -> Page[SubscriberOut]:
    items, total = await telegram_service.list_subscribers(
        session, user.id, page=page, page_size=page_size
    )
    return Page[SubscriberOut](items=items, total=total)


@router.get("/broadcasts", response_model=Page[BroadcastOut])
async def list_broadcasts(
    session: DbSession,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[BroadcastOut]:
    items, total = await telegram_service.list_broadcasts(
        session, user.id, page=page, page_size=page_size
    )
    return Page[BroadcastOut](items=items, total=total)


@router.post("/broadcasts", response_model=BroadcastOut, status_code=status.HTTP_201_CREATED)
async def create_broadcast(session: DbSession, user: CurrentUser, body: BroadcastIn) -> BroadcastOut:
    return await telegram_service.create_broadcast(session, user.id, body)
