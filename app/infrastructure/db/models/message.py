"""The messages ledger — the highest-volume table in the system.

Design decisions:

- **Partitioned by RANGE (created_at)** (monthly partitions + a DEFAULT
  catch-all), so old months can be detached/archived without DELETEs and the
  hot working set stays small. New partitions must be added monthly (cron or
  pg_partman) — see migration 0001.
- **Composite PK (id, created_at)**: PostgreSQL requires the partition key in
  any unique constraint on a partitioned table. ``id`` alone is still
  globally unique in practice (single identity sequence).
- **Append-only**: rows are inserted and their status columns updated, never
  deleted.
- ``priority`` is a smallint rank (0=urgent, 1=transactional, 2=bulk — see
  ``app.domain.enums.PRIORITY_RANK``) so the queue index sorts cheaply.
- ``lease_expires_at`` implements at-least-once delivery to gateway devices:
  a device claims a batch (status -> 'sending', lease set); if it never
  reports back, the sweeper returns expired leases to 'queued'.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_user_created", "user_id", text("created_at DESC")),
        Index(
            "ix_messages_queue",
            "device_id",
            "priority",
            "created_at",
            postgresql_where=text("status IN ('queued', 'sending')"),
        ),
        Index("ix_messages_status", "status"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        server_default=func.now(),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Nullable: bulk sends are queued before a device is picked; SET NULL keeps
    # the ledger intact even if a device row were ever hard-removed.
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    text_: Mapped[str] = mapped_column("text", Text, nullable=False)
    segments: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="queued")
    # 0=urgent, 1=transactional, 2=bulk (PRIORITY_RANK).
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fail_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
