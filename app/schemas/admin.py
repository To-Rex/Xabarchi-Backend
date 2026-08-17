"""Admin-panel DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.enums import InvoiceStatus, PlanId
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
