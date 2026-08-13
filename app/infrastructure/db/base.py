"""Declarative base and shared model mixins.

DURABILITY RULES (enforced across the schema — do not weaken):

1. No ``ON DELETE CASCADE`` from ``users``: every user-owned table references
   ``users.id`` with ``ondelete="RESTRICT"``. A user with data can never be
   hard-deleted by accident; account removal is an explicit, audited process.
2. Soft deletes everywhere user data lives: rows get ``deleted_at`` set
   instead of being removed (``api_keys`` uses ``revoked_at`` — same idea).
   Queries must always filter ``deleted_at IS NULL``.
3. ``messages`` (and ``bot_broadcasts``) are append-only ledgers: rows are
   inserted and their status columns updated, but NEVER deleted. Old data
   ages out by detaching monthly partitions, not by DELETE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Root declarative base; all models inherit from this."""

    type_annotation_map = {
        # All datetimes are timestamptz stored as UTC.
        datetime: DateTime(timezone=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    """Standard UUID primary key column with a client-side uuid4 default."""
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """``created_at``/``updated_at`` timestamptz maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Soft-delete marker; a non-NULL ``deleted_at`` means the row is gone."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
