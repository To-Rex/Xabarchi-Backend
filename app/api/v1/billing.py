"""Billing routes: plan catalogue, invoices, Polar checkout + webhook."""

from __future__ import annotations

import orjson
from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession
from app.repositories import billing_repo
from app.schemas.billing import CheckoutIn, CheckoutOut, InvoiceOut, PlanOut, PortalOut
from app.services import polar_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(session: DbSession) -> list[PlanOut]:
    plans = await billing_repo.list_plans(session)
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(session: DbSession, user: CurrentUser) -> list[InvoiceOut]:
    invoices = await billing_repo.list_invoices(session, user.id)
    return [InvoiceOut.model_validate(i) for i in invoices]


@router.post("/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
async def create_checkout(user: CurrentUser, body: CheckoutIn) -> CheckoutOut:
    """Create a Polar checkout session for a paid plan; returns its URL."""
    url = await polar_service.create_checkout(user, body.plan_id.value)
    return CheckoutOut(url=url)


@router.get("/portal", response_model=PortalOut)
async def customer_portal(user: CurrentUser) -> PortalOut:
    """Polar customer-portal session for managing the subscription."""
    url = await polar_service.create_portal_url(user)
    return PortalOut(url=url)


@router.post("/webhook/polar", include_in_schema=False)
async def polar_webhook(session: DbSession, request: Request) -> dict[str, str]:
    """Polar webhook sink — authenticated by its Standard Webhooks signature."""
    body = await request.body()
    polar_service.verify_webhook(body, dict(request.headers))
    await polar_service.handle_event(session, orjson.loads(body))
    return {"status": "ok"}
