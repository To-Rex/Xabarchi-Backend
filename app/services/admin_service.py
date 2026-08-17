"""Admin-panel business logic: overview, user/device/plan/invoice management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.domain.enums import NotificationKind, NotificationSeverity
from app.infrastructure.db.models import Device, Plan, User
from app.repositories import admin_repo, billing_repo, user_repo
from app.schemas.admin import (
    AdminDeviceOut,
    AdminInvoiceOut,
    AdminOverviewOut,
    AdminUserOut,
    AdminUserUpdateIn,
    DiscountCreateIn,
    NotifyIn,
    PlanSyncOut,
    PlanUpdateIn,
)
from app.schemas.billing import PlanOut
from app.services import notification_service, polar_service


def _user_out(user: User, device_count: int) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        company=user.company,
        role=user.role,
        plan_id=user.plan_id,
        plan_active=user.plan_active,
        plan_expires_at=user.plan_expires_at,
        email_verified=user.email_verified,
        is_admin=user.is_admin,
        sms_sent_this_month=user.sms_sent_this_month,
        device_count=device_count,
        created_at=user.created_at,
        deleted_at=user.deleted_at,
    )


async def overview(session: AsyncSession) -> AdminOverviewOut:
    data = await admin_repo.overview(session)
    return AdminOverviewOut(**data)


async def list_users(
    session: AsyncSession,
    *,
    search: str | None,
    page: int,
    page_size: int,
    include_deleted: bool = False,
) -> tuple[list[AdminUserOut], int]:
    users, total = await admin_repo.list_users(
        session, search=search, page=page, page_size=page_size, include_deleted=include_deleted
    )
    counts = await admin_repo.device_counts(session, [u.id for u in users])
    return [_user_out(u, counts.get(u.id, 0)) for u in users], total


async def reset_quota(session: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    await user_repo.update(session, user, {"sms_sent_this_month": 0})
    counts = await admin_repo.device_counts(session, [user.id])
    return _user_out(user, counts.get(user.id, 0))


async def restore_user(session: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.deleted_at is not None:
        await user_repo.update(session, user, {"deleted_at": None})
    counts = await admin_repo.device_counts(session, [user.id])
    return _user_out(user, counts.get(user.id, 0))


async def notify_user(session: AsyncSession, user_id: uuid.UUID, data: NotifyIn) -> None:
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    await notification_service.create(
        session,
        user.id,
        kind=NotificationKind.system,
        severity=NotificationSeverity(data.severity),
        title={"uz": data.title, "ru": data.title, "en": data.title},
        body={"uz": data.body, "ru": data.body, "en": data.body},
    )


async def create_discount(data: DiscountCreateIn) -> dict[str, object]:
    try:
        return await polar_service.create_discount(
            name=data.name,
            kind=data.kind,
            value=data.value,
            code=data.code,
            duration=data.duration,
            plan_id=data.plan_id.value if data.plan_id else None,
        )
    except AppError as exc:
        detail = getattr(exc, "polar_detail", "")
        if detail:
            raise AppError(f"Polar: {detail[:200]}", code=exc.code, status=exc.status) from exc
        raise


async def list_discounts() -> list[dict[str, object]]:
    return await polar_service.list_discounts()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> AdminUserOut:
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    counts = await admin_repo.device_counts(session, [user.id])
    return _user_out(user, counts.get(user.id, 0))


async def update_user(
    session: AsyncSession, actor: User, user_id: uuid.UUID, data: AdminUserUpdateIn
) -> AdminUserOut:
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")

    provided = data.model_dump(exclude_unset=True)
    updates: dict[str, object] = {}
    if "plan_id" in provided and data.plan_id is not None:
        updates["plan_id"] = data.plan_id.value
    if "plan_expires_at" in provided:
        updates["plan_expires_at"] = data.plan_expires_at  # None clears it
    if "role" in provided and data.role:
        updates["role"] = data.role
    if "email_verified" in provided:
        updates["email_verified_at"] = datetime.now(UTC) if data.email_verified else None

    if updates:
        await user_repo.update(session, user, updates)
    counts = await admin_repo.device_counts(session, [user.id])
    return _user_out(user, counts.get(user.id, 0))


async def delete_user(session: AsyncSession, actor: User, user_id: uuid.UUID) -> None:
    if actor.id == user_id:
        raise AppError("You can't delete your own account", code="self_delete", status=400)
    user = await admin_repo.get_user(session, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.deleted_at is None:
        await user_repo.update(session, user, {"deleted_at": datetime.now(UTC)})


async def list_devices(
    session: AsyncSession, *, page: int, page_size: int
) -> tuple[list[AdminDeviceOut], int]:
    rows, total = await admin_repo.list_devices(session, page=page, page_size=page_size)
    items = [_device_out(device, email, company) for device, email, company in rows]
    return items, total


def _device_out(device: Device, owner_email: str, owner_company: str) -> AdminDeviceOut:
    return AdminDeviceOut(
        id=device.id,
        name=device.name,
        model=device.model,
        phone=device.phone,
        operator=device.operator,
        status=device.status,
        battery=device.battery,
        signal=device.signal,
        sent_today=device.sent_today,
        daily_limit=device.daily_limit,
        last_seen_at=device.last_seen_at,
        owner_email=owner_email,
        owner_company=owner_company,
    )


async def list_invoices(
    session: AsyncSession, *, page: int, page_size: int
) -> tuple[list[AdminInvoiceOut], int]:
    rows, total = await admin_repo.list_invoices(session, page=page, page_size=page_size)
    items = [
        AdminInvoiceOut(
            id=inv.id,
            number=inv.number,
            date=inv.date,
            amount=inv.amount,
            status=inv.status,
            plan_id=inv.plan_id,
            period=inv.period,
            owner_email=email,
            owner_company=company,
        )
        for inv, email, company in rows
    ]
    return items, total


async def list_plans(session: AsyncSession) -> list[PlanOut]:
    plans = await billing_repo.list_plans(session)
    return [PlanOut.model_validate(p) for p in plans]


async def update_plan(session: AsyncSession, plan_id: str, data: PlanUpdateIn) -> PlanSyncOut:
    plan: Plan | None = await billing_repo.get_plan(session, plan_id)
    if plan is None:
        raise NotFoundError("Plan not found")
    fields = data.model_dump(exclude_unset=True)
    fields.pop("sync_to_polar", None)  # not a Plan column
    for key, value in fields.items():
        if value is not None:
            setattr(plan, key, value)
    await session.flush()

    # Optionally mirror the new price to the plan's Polar product (best-effort).
    polar_sync = "skipped"
    if data.sync_to_polar and "monthly_price" in fields and fields["monthly_price"] is not None:
        polar_sync = await polar_service.sync_product_price(plan_id, plan.monthly_price)

    return PlanSyncOut(plan=PlanOut.model_validate(plan), polar_sync=polar_sync)
