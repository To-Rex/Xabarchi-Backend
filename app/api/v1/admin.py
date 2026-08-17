"""Admin-panel routes — every endpoint requires admin access (AdminUser)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, DbSession
from app.schemas.admin import (
    AdminDeviceOut,
    AdminInvoiceOut,
    AdminOverviewOut,
    AdminUserOut,
    AdminUserUpdateIn,
    PlanUpdateIn,
)
from app.schemas.billing import PlanOut
from app.schemas.common import Page
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewOut)
async def overview(session: DbSession, _: AdminUser) -> AdminOverviewOut:
    return await admin_service.overview(session)


@router.get("/users", response_model=Page[AdminUserOut])
async def list_users(
    session: DbSession,
    _: AdminUser,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[AdminUserOut]:
    items, total = await admin_service.list_users(
        session, search=search, page=page, page_size=page_size
    )
    return Page[AdminUserOut](items=items, total=total)


@router.get("/users/{user_id}", response_model=AdminUserOut)
async def get_user(session: DbSession, _: AdminUser, user_id: uuid.UUID) -> AdminUserOut:
    return await admin_service.get_user(session, user_id)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    session: DbSession, admin: AdminUser, user_id: uuid.UUID, body: AdminUserUpdateIn
) -> AdminUserOut:
    return await admin_service.update_user(session, admin, user_id, body)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(session: DbSession, admin: AdminUser, user_id: uuid.UUID) -> None:
    await admin_service.delete_user(session, admin, user_id)


@router.get("/devices", response_model=Page[AdminDeviceOut])
async def list_devices(
    session: DbSession,
    _: AdminUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[AdminDeviceOut]:
    items, total = await admin_service.list_devices(session, page=page, page_size=page_size)
    return Page[AdminDeviceOut](items=items, total=total)


@router.get("/invoices", response_model=Page[AdminInvoiceOut])
async def list_invoices(
    session: DbSession,
    _: AdminUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[AdminInvoiceOut]:
    items, total = await admin_service.list_invoices(session, page=page, page_size=page_size)
    return Page[AdminInvoiceOut](items=items, total=total)


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(session: DbSession, _: AdminUser) -> list[PlanOut]:
    return await admin_service.list_plans(session)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    session: DbSession, _: AdminUser, plan_id: str, body: PlanUpdateIn
) -> PlanOut:
    return await admin_service.update_plan(session, plan_id, body)
