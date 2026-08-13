"""Analytics routes for the dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.analytics import DailyStatOut, OverviewOut
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewOut)
async def overview(session: DbSession, user: CurrentUser) -> OverviewOut:
    return await analytics_service.overview(session, user)


@router.get("/daily", response_model=list[DailyStatOut])
async def daily(
    session: DbSession,
    user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[DailyStatOut]:
    return await analytics_service.daily_stats(session, user, days=days)
