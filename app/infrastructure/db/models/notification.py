"""In-app notifications with localized JSONB payloads ({uz, ru, en})."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, uuid_pk


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_read_created", "user_id", "read", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 'device' | 'billing' | 'system' | 'sms'.
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    # 'info' | 'success' | 'warn' | 'error'.
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    # Localized: {"uz": ..., "ru": ..., "en": ...}.
    title: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    body: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    read: Mapped[bool] = mapped_column(nullable=False, default=False)
