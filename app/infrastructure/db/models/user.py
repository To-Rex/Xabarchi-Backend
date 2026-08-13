"""User accounts (one row per company owner/member) and OAuth links."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # NULL for social-only accounts (they have no password to check).
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # Polar customer id, learned from the first checkout/webhook.
    polar_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    @property
    def email_verified(self) -> bool:
        """Serialized into UserOut — pydantic reads properties too."""
        return self.email_verified_at is not None


# Case-insensitive email uniqueness without requiring the citext extension.
Index("uq_users_email_lower", func.lower(User.email), unique=True)


class OAuthAccount(Base, TimestampMixin):
    """Link between a user and an external identity (Google / Apple).

    ``subject`` is the provider's stable user id (OIDC ``sub``) — the pair
    (provider, subject) identifies one external identity exactly once.
    """

    __tablename__ = "oauth_accounts"
    __table_args__ = (Index("uq_oauth_provider_subject", "provider", "subject", unique=True),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
