"""Gateway devices: the user's Android phones that actually send SMS."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class Device(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_user_deleted", "user_id", "deleted_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    operator: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="offline")
    connection: Mapped[str] = mapped_column(String(8), nullable=False, default="offline")
    battery: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    # 0..4 bars, matching the frontend signal indicator.
    signal: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    android_version: Mapped[str] = mapped_column(String(8), nullable=False)
    app_version: Mapped[str] = mapped_column(String(16), nullable=False)
    sent_today: Mapped[int] = mapped_column(nullable=False, default=0)
    daily_limit: Mapped[int] = mapped_column(nullable=False, default=500)
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    # SHA-256 of the device auth token; NULL until the device is enrolled.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
