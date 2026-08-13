"""Telegram integration: company bots, their subscribers, and broadcasts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class TelegramBot(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "telegram_bots"
    __table_args__ = (
        # One live bot per user; soft-deleted bots don't block reconnecting.
        Index(
            "uq_telegram_bots_user_live",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # @username handle, without the @.
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="active")
    # SHA-256 of the BotFather token; the plaintext token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    webhook_ok: Mapped[bool] = mapped_column(nullable=False, default=True)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BotSubscriber(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "bot_subscribers"

    id: Mapped[uuid.UUID] = uuid_pk()
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_bots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    avatar_hue: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # How the subscriber found the bot: 'link' | 'qr' | 'search'.
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class BotBroadcast(Base):
    """Broadcast ledger; append-only like ``messages`` (no soft delete)."""

    __tablename__ = "bot_broadcasts"
    __table_args__ = (Index("ix_bot_broadcasts_bot_created", "bot_id", text("created_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    bot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("telegram_bots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 'text' | 'photo' | 'video' | 'document' | 'post'.
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    # Message text, or the caption for media kinds.
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    media_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    button_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    button_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    audience: Mapped[int] = mapped_column(nullable=False, default=0)
    delivered: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
