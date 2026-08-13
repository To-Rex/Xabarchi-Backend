"""Billing: subscription plans (reference data) and invoices."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin, uuid_pk


class Plan(Base):
    """Reference table seeded in migration 0001 (start / biznes / korxona)."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    # Prices are stored in UZS (integer so'm) — no fractional currency unit.
    monthly_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sms_per_month: Mapped[int] = mapped_column(nullable=False)
    max_devices: Mapped[int] = mapped_column(nullable=False)
    api_access: Mapped[bool] = mapped_column(nullable=False, default=False)
    priority_support: Mapped[bool] = mapped_column(nullable=False, default=False)


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Human-facing invoice number like "INV-2026-0042".
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # UZS (integer so'm).
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 'paid' | 'due' | 'failed'.
    status: Mapped[str] = mapped_column(String(8), nullable=False)
    plan_id: Mapped[str] = mapped_column(
        String(16),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Billed period label like "2026-08" or "Avgust 2026".
    period: Mapped[str] = mapped_column(String(32), nullable=False)
