"""User accounts (one row per company owner/member)."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="owner")
    avatar_hue: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=172)
    plan_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
        default="start",
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Tashkent")
    sms_sent_this_month: Mapped[int] = mapped_column(nullable=False, default=0)


# Case-insensitive email uniqueness without requiring the citext extension.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
