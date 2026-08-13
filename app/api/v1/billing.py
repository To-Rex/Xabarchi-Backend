"""Billing routes: plan catalogue and invoice history."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.repositories import billing_repo
from app.schemas.billing import InvoiceOut, PlanOut

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(session: DbSession) -> list[PlanOut]:
    plans = await billing_repo.list_plans(session)
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(session: DbSession, user: CurrentUser) -> list[InvoiceOut]:
    invoices = await billing_repo.list_invoices(session, user.id)
    return [InvoiceOut.model_validate(i) for i in invoices]
