"""Billing DTOs: plans and invoices."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.domain.enums import InvoiceStatus, PlanId
from app.schemas.common import CamelModel


class PlanOut(CamelModel):
    id: PlanId
    monthly_price: int
    sms_per_month: int
    max_devices: int
    api_access: bool
    priority_support: bool


class InvoiceOut(CamelModel):
    id: uuid.UUID
    number: str
    date: datetime
    amount: int
    status: InvoiceStatus
    plan_id: PlanId
    period: str


class CheckoutIn(CamelModel):
    """Start a Polar checkout for one of the paid plans."""

    plan_id: PlanId


class CheckoutOut(CamelModel):
    """Hosted checkout URL — the frontend redirects the browser to it."""

    url: str


class PortalOut(CamelModel):
    """Polar customer-portal URL for managing the subscription."""

    url: str
