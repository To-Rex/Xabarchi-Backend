"""Telegram bot integration DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import AliasChoices, Field

from app.domain.enums import BotMessageKind, BroadcastStatus
from app.schemas.common import CamelModel


class BotConnectIn(CamelModel):
    token: str = Field(min_length=1, max_length=128)


class BotOut(CamelModel):
    id: uuid.UUID
    username: str
    title: str
    status: str
    connected_at: datetime
    subscriber_count: int
    webhook_ok: bool


class SubscriberOut(CamelModel):
    id: uuid.UUID
    name: str
    username: str | None = None
    joined_at: datetime
    avatar_hue: int
    source: str


class BroadcastIn(CamelModel):
    kind: BotMessageKind
    text: str = Field(min_length=1, max_length=4096)
    media_name: str | None = Field(default=None, max_length=255)
    button_label: str | None = Field(default=None, max_length=64)
    button_url: str | None = Field(default=None, max_length=2048)


class BroadcastOut(CamelModel):
    id: int
    kind: BotMessageKind
    # ORM attribute is ``text_`` (column "text"); also accept plain "text".
    text: str = Field(validation_alias=AliasChoices("text", "text_"))
    media_name: str | None = None
    button_label: str | None = None
    button_url: str | None = None
    audience: int
    delivered: int
    created_at: datetime
    status: BroadcastStatus
