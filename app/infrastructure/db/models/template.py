"""Reusable SMS templates with {placeholder} variables."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class Template(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Placeholder names like {ism}, {kod} extracted from the text.
    variables: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    used_count: Mapped[int] = mapped_column(nullable=False, default=0)
