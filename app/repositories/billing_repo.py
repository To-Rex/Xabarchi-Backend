"""Billing data access: plans (reference data) and invoices."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
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


async def get_invoice_by_external_id(session: AsyncSession, external_id: str) -> Invoice | None:
    stmt = select(Invoice).where(Invoice.external_id == external_id)
    return await session.scalar(stmt)


async def count_invoices(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Invoice)) or 0)


async def create_invoice(session: AsyncSession, **fields: Any) -> Invoice:
    invoice = Invoice(**fields)
    session.add(invoice)
    await session.flush()
    return invoice
