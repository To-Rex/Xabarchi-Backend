"""In-app notification DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.domain.enums import NotificationKind, NotificationSeverity
from app.schemas.common import CamelModel


class LocalizedText(CamelModel):
    uz: str
    ru: str
    en: str


class NotificationOut(CamelModel):
    id: uuid.UUID
    kind: NotificationKind
    severity: NotificationSeverity
    title: LocalizedText
    body: LocalizedText
    created_at: datetime
    read: bool


class UnreadCountOut(CamelModel):
    unread: int
