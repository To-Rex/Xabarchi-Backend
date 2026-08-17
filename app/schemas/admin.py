"""Admin-panel DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.domain.enums import InvoiceStatus, PlanId
from app.schemas.billing import PlanOut
from app.schemas.common import CamelModel


class AdminOverviewOut(CamelModel):
    total_users: int
    paid_users: int
    total_devices: int
    online_devices: int
    messages_today: int
    messages_month: int
    delivered_month: int
    total_bots: int
    revenue_month: int
    plan_counts: dict[str, int]


class AdminUserOut(CamelModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    phone: str
    company: str
    role: str
    plan_id: PlanId
    plan_active: bool
    plan_expires_at: datetime | None
    email_verified: bool
    is_admin: bool
    sms_sent_this_month: int
    device_count: int
    created_at: datetime
    deleted_at: datetime | None


class AdminDeviceOut(CamelModel):
    id: uuid.UUID
    name: str
    model: str
    phone: str
    operator: str
    status: str
    battery: int
    signal: int
    sent_today: int
    daily_limit: int
    last_seen_at: datetime | None
    owner_email: str
    owner_company: str


class AdminInvoiceOut(CamelModel):
    id: uuid.UUID
    number: str
    date: datetime
    amount: int
    status: InvoiceStatus
    plan_id: PlanId
    period: str
    owner_email: str
    owner_company: str


class AdminUserUpdateIn(CamelModel):
    """All fields optional — only the provided ones are changed."""

    plan_id: PlanId | None = None
    plan_expires_at: datetime | None = None
    email_verified: bool | None = None
    role: str | None = Field(default=None, max_length=20)


class PlanUpdateIn(CamelModel):
    monthly_price: int | None = Field(default=None, ge=0)
    sms_per_month: int | None = Field(default=None, ge=0)
    max_devices: int | None = Field(default=None, ge=0)
    api_access: bool | None = None
    priority_support: bool | None = None
    # When true, also push the (new) price to the plan's Polar product.
    sync_to_polar: bool = False


class PlanSyncOut(CamelModel):
    """Plan after an admin update, plus the Polar-sync outcome."""

    plan: PlanOut
    polar_sync: str  # "synced" | "polar_disabled" | "not_purchasable" | "error:*" | "skipped"


class DiscountCreateIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["percentage", "fixed"] = "percentage"
    # percentage: 0–100; fixed: amount in the currency's minor units.
    value: int = Field(ge=0)
    code: str | None = Field(default=None, max_length=64)
    duration: Literal["once", "forever", "repeating"] = "once"
    plan_id: PlanId | None = None


class NotifyIn(CamelModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    severity: Literal["info", "success", "warn", "error"] = "info"
