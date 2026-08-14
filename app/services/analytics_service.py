"""Dashboard analytics: overview snapshot and daily series."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import DeviceStatus
from app.infrastructure.db.models import User
from app.repositories import billing_repo, device_repo, message_repo
from app.schemas.analytics import DailyStatOut, OverviewOut
from app.schemas.device import DeviceOut
from app.schemas.message import MessageOut
from app.services import subscription_service


async def daily_stats(session: AsyncSession, user: User, days: int = 30) -> list[DailyStatOut]:
    rows = await message_repo.daily_stats(session, user.id, days=days)
    return [DailyStatOut.model_validate(row) for row in rows]


async def overview(session: AsyncSession, user: User) -> OverviewOut:
    """Everything the dashboard overview page renders, in one response."""
    counts = await message_repo.overview_counts(session, user.id)
    devices = await device_repo.list_for_user(session, user.id)
    series = await daily_stats(session, user, days=30)
    recent = await message_repo.recent(session, user.id, limit=6)
    plan = await billing_repo.get_plan(session, subscription_service.effective_plan_id(user))

    delivery_rate = (
        counts["delivered_30d"] / counts["sent_30d"] * 100 if counts["sent_30d"] else 0.0
    )
    return OverviewOut(
        sent_today=counts["sent_today"],
        sent_yesterday=counts["sent_yesterday"],
        delivery_rate=round(delivery_rate, 2),
        active_devices=sum(1 for d in devices if d.status == DeviceStatus.online.value),
        total_devices=len(devices),
        queued=counts["queued"],
        monthly_used=user.sms_sent_this_month,
        monthly_limit=plan.sms_per_month if plan is not None else 0,
        series=series,
        recent_messages=[MessageOut.model_validate(m) for m in recent],
        devices=[DeviceOut.model_validate(d) for d in devices],
    )
