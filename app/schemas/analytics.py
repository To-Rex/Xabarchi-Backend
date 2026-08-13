"""Analytics DTOs matching the dashboard Overview contract."""

from __future__ import annotations

from datetime import date as date_type

from app.schemas.common import CamelModel
from app.schemas.device import DeviceOut
from app.schemas.message import MessageOut


class DailyStatOut(CamelModel):
    """One row of the ``daily_stats`` view (frontend DailyStat)."""

    date: date_type
    sent: int
    delivered: int
    failed: int


class OverviewOut(CamelModel):
    """Frontend ``OverviewData`` contract (dashboard overview page)."""

    sent_today: int
    sent_yesterday: int
    delivery_rate: float
    active_devices: int
    total_devices: int
    queued: int
    monthly_used: int
    monthly_limit: int
    series: list[DailyStatOut]
    recent_messages: list[MessageOut]
    devices: list[DeviceOut]
