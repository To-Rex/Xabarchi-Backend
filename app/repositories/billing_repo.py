"""Billing data access: plans (reference data) and invoices."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Invoice, Plan


async def list_plans(session: AsyncSession) -> list[Plan]:
    stmt = select(Plan).order_by(Plan.monthly_price)
    return list((await session.scalars(stmt)).all())


async def get_plan(session: AsyncSession, plan_id: str) -> Plan | None:
    return await session.get(Plan, plan_id)


async def list_invoices(session: AsyncSession, user_id: uuid.UUID) -> list[Invoice]:
    stmt = select(Invoice).where(Invoice.user_id == user_id).order_by(Invoice.date.desc())
    return list((await session.scalars(stmt)).all())
