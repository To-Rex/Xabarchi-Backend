"""Polar (polar.sh) billing: checkout sessions, customer portal, webhooks.

Flow:

1. Dashboard calls ``POST /billing/checkout {planId}`` -> we create a Polar
   checkout session (the plan's product id) and return its hosted ``url``.
   ``external_customer_id`` and ``metadata.user_id`` both carry our user id,
   so every later webhook can be traced back to the account.
2. Polar calls ``POST /billing/webhook/polar`` (Standard Webhooks signature).
   ``order.paid`` records an invoice (idempotent on the order id) and
   activates the plan; ``subscription.active`` re-activates it on renewals;
   ``subscription.revoked`` drops the account back to the free plan.
3. ``GET /billing/portal`` mints a customer-portal session so users manage
   their subscription/payment methods on Polar's hosted portal.

Empty ``POLAR_ACCESS_TOKEN`` disables the integration with a clear 503.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthError
from app.domain.enums import NotificationKind, NotificationSeverity, PlanId
from app.infrastructure.db.models import User
from app.repositories import billing_repo, user_repo
from app.services import notification_service

logger = logging.getLogger(__name__)

# Only paid plans are purchasable; "start" is the free fallback.
_PAID_PLANS = (PlanId.biznes, PlanId.korxona)

_WEBHOOK_TOLERANCE_SECONDS = 300
# Fallback entitlement length when the payload carries no explicit period end.
_DEFAULT_PERIOD_DAYS = 31


def _base_url() -> str:
    return (
        "https://sandbox-api.polar.sh"
        if settings.polar_server == "sandbox"
        else "https://api.polar.sh"
    )


def _ensure_enabled() -> None:
    if not settings.polar_access_token:
        raise AppError(
            "Polar billing is not configured on this server",
            code="billing_not_configured",
            status=503,
        )


def _product_for_plan(plan_id: str) -> str:
    product = {
        PlanId.biznes.value: settings.polar_product_biznes,
        PlanId.korxona.value: settings.polar_product_korxona,
    }.get(plan_id, "")
    if not product:
        raise AppError(
            f"Plan '{plan_id}' cannot be purchased online",
            code="plan_not_purchasable",
            status=400,
        )
    return product


def _plan_for_product(product_id: str) -> str | None:
    if product_id and product_id == settings.polar_product_biznes:
        return PlanId.biznes.value
    if product_id and product_id == settings.polar_product_korxona:
        return PlanId.korxona.value
    return None


async def _polar_request(
    method: str, path: str, payload: dict[str, object] | None = None
) -> dict[str, object]:
    # Bind outbound sockets to the IPv4 wildcard so the request never picks a
    # (frequently broken in containers) IPv6 route to Polar/Cloudflare — that
    # path connects but never returns, surfacing as an httpx.ReadTimeout.
    transport = httpx.AsyncHTTPTransport(local_address="0.0.0.0")
    timeout = httpx.Timeout(20.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.request(
                method,
                f"{_base_url()}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {settings.polar_access_token}"},
            )
    except httpx.TimeoutException as exc:
        logger.error("Polar %s %s timed out: %s", method, path, exc)
        raise AppError(
            "Polar did not respond in time — please try again",
            code="polar_timeout",
            status=504,
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Polar %s %s transport error: %s", method, path, exc)
        raise AppError("Couldn't reach Polar", code="polar_unreachable", status=502) from exc
    if response.status_code not in (200, 201):
        detail = response.text[:400]
        logger.error("Polar %s %s failed: %s %s", method, path, response.status_code, detail)
        err = AppError("Polar request failed", code="polar_error", status=502)
        err.polar_detail = detail  # type: ignore[attr-defined]
        raise err
    return response.json() if response.content else {}


async def _polar_post(path: str, payload: dict[str, object]) -> dict[str, object]:
    return await _polar_request("POST", path, payload)


async def _polar_get(path: str) -> dict[str, object]:
    return await _polar_request("GET", path)


async def _polar_patch(path: str, payload: dict[str, object]) -> dict[str, object]:
    return await _polar_request("PATCH", path, payload)


# --------------------------------------------------------- discounts / pricing

def _currency() -> str:
    """Currency for Polar prices/discounts (configurable; default UZS)."""
    return (settings.polar_currency or "uzs").lower()


async def create_discount(
    *,
    name: str,
    kind: str,
    value: int,
    code: str | None = None,
    duration: str = "once",
    plan_id: str | None = None,
) -> dict[str, object]:
    """Create a Polar discount.

    ``kind`` is "percentage" (value = percent, 0–100) or "fixed" (value = amount
    in the currency's minor units). ``plan_id`` optionally restricts it to that
    plan's product. ``code`` makes it a redeemable coupon; omit for an automatic one.
    """
    _ensure_enabled()
    payload: dict[str, object] = {"name": name, "duration": duration}
    if kind == "percentage":
        payload["type"] = "percentage"
        payload["basis_points"] = max(0, min(100, value)) * 100  # 10% -> 1000
    else:
        payload["type"] = "fixed"
        payload["amount"] = max(0, value)
        payload["currency"] = _currency()
    if code:
        payload["code"] = code
    if settings.polar_organization_id:
        payload["organization_id"] = settings.polar_organization_id
    if plan_id:
        try:
            payload["products"] = [_product_for_plan(plan_id)]
        except AppError:
            pass
    return await _polar_post("/v1/discounts/", payload)


async def list_discounts() -> list[dict[str, object]]:
    """List existing Polar discounts (best-effort; empty on any issue)."""
    _ensure_enabled()
    org = f"&organization_id={settings.polar_organization_id}" if settings.polar_organization_id else ""
    data = await _polar_get(f"/v1/discounts/?limit=100{org}")
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


async def sync_product_price(plan_id: str, monthly_price: int) -> str:
    """Best-effort: push a plan's new price to its Polar product.

    Returns a status the admin UI can show — never raises, so a price edit can
    never break because of Polar. Polar prices are immutable, so this PATCHes the
    product with a fresh fixed recurring price (Polar archives the previous one).
    Note: ``monthly_price`` is sent as-is in minor units; verify the currency in
    Polar if your product isn't priced in the same unit.
    """
    if not settings.polar_access_token:
        return "polar_disabled"
    try:
        product_id = _product_for_plan(plan_id)
    except AppError:
        return "not_purchasable"
    try:
        await _polar_patch(
            f"/v1/products/{product_id}",
            {
                "prices": [
                    {
                        "amount_type": "fixed",
                        "price_amount": int(monthly_price),
                        "price_currency": _currency(),
                    }
                ]
            },
        )
        return "synced"
    except AppError as exc:
        detail = getattr(exc, "polar_detail", "") or exc.code
        logger.warning("Polar price sync failed for plan %s: %s", plan_id, detail)
        return f"error:{detail[:200]}"


async def create_checkout(user: User, plan_id: str) -> str:
    """Create a hosted checkout session; returns the URL to redirect to."""
    _ensure_enabled()
    data = await _polar_post(
        "/v1/checkouts/",
        {
            "products": [_product_for_plan(plan_id)],
            "success_url": f"{settings.frontend_url}/app/billing?checkout=success",
            "customer_email": user.email,
            "external_customer_id": str(user.id),
            "metadata": {"user_id": str(user.id), "plan_id": plan_id},
        },
    )
    return str(data["url"])


async def create_portal_url(user: User) -> str:
    """Customer-portal session URL for managing the subscription on Polar."""
    _ensure_enabled()
    data = await _polar_post(
        "/v1/customer-sessions/",
        {
            "external_customer_id": str(user.id),
            "return_url": f"{settings.frontend_url}/app/billing",
        },
    )
    return str(data["customer_portal_url"])


# --------------------------------------------------------------- webhooks


def verify_webhook(body: bytes, headers: dict[str, str]) -> None:
    """Standard Webhooks signature check (HMAC-SHA256 over id.timestamp.body).

    Raises AuthError unless one ``v1,<sig>`` entry matches and the timestamp
    is within tolerance. Polar secrets may carry a ``polar_whs_``/``whsec_``
    prefix and are base64-encoded.
    """
    if not settings.polar_webhook_secret:
        raise AuthError("Webhook secret not configured")
    webhook_id = headers.get("webhook-id", "")
    timestamp = headers.get("webhook-timestamp", "")
    signature_header = headers.get("webhook-signature", "")
    if not webhook_id or not timestamp or not signature_header:
        raise AuthError("Missing webhook signature headers")

    try:
        if abs(time.time() - int(timestamp)) > _WEBHOOK_TOLERANCE_SECONDS:
            raise AuthError("Webhook timestamp outside tolerance")
    except ValueError as exc:
        raise AuthError("Invalid webhook timestamp") from exc

    secret = settings.polar_webhook_secret
    for prefix in ("polar_whs_", "whsec_"):
        if secret.startswith(prefix):
            secret = secret[len(prefix) :]
            break
    try:
        key = base64.b64decode(secret + "=" * (-len(secret) % 4))
    except Exception:  # noqa: BLE001 - some setups store the raw secret
        key = secret.encode()

    signed = f"{webhook_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()

    for candidate in signature_header.split(" "):
        version, _, signature = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(signature, expected):
            return
    raise AuthError("Webhook signature mismatch")


async def _resolve_user(session: AsyncSession, data: dict[str, object]) -> User | None:
    """Find our user from a webhook payload (metadata, external id, e-mail)."""
    metadata = data.get("metadata") or {}
    customer = data.get("customer") or {}
    for raw in (
        metadata.get("user_id") if isinstance(metadata, dict) else None,
        customer.get("external_id") if isinstance(customer, dict) else None,
    ):
        if raw:
            try:
                user = await user_repo.get_by_id(session, uuid.UUID(str(raw)))
            except ValueError:
                user = None
            if user is not None:
                return user
    email = customer.get("email") if isinstance(customer, dict) else None
    if email:
        return await user_repo.get_by_email(session, str(email))
    return None


def _event_plan(data: dict[str, object]) -> str | None:
    """Plan bought: prefer checkout metadata, fall back to the product map."""
    metadata = data.get("metadata") or {}
    if isinstance(metadata, dict):
        plan_id = str(metadata.get("plan_id") or "")
        if plan_id in {p.value for p in _PAID_PLANS}:
            return plan_id
    product = data.get("product") or {}
    product_id = str(product.get("id") or "") if isinstance(product, dict) else ""
    return _plan_for_product(product_id or str(data.get("product_id") or ""))


def _parse_dt(raw: object) -> datetime | None:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _period_end(data: dict[str, object]) -> datetime:
    """When the entitlement should lapse.

    Prefers Polar's ``current_period_end`` (on the subscription, or nested in an
    order payload); falls back to ~1 month out so a paid account is never left
    without an expiry.
    """
    candidate = _parse_dt(data.get("current_period_end") or data.get("ends_at"))
    if candidate is None:
        subscription = data.get("subscription")
        if isinstance(subscription, dict):
            candidate = _parse_dt(subscription.get("current_period_end"))
    return candidate or datetime.now(UTC) + timedelta(days=_DEFAULT_PERIOD_DAYS)


async def _activate(
    session: AsyncSession, user: User, data: dict[str, object], plan_id: str | None
) -> None:
    """Apply a paid plan: set/refresh the expiry and reset the monthly quota."""
    updates: dict[str, object] = {
        "plan_expires_at": _period_end(data),
        "sms_sent_this_month": 0,
    }
    if plan_id and user.plan_id != plan_id:
        updates["plan_id"] = plan_id
    await user_repo.update(session, user, updates)


async def _remember_customer_id(session: AsyncSession, user: User, data: dict[str, object]) -> None:
    customer = data.get("customer") or {}
    customer_id = str(customer.get("id") or "") if isinstance(customer, dict) else ""
    if customer_id and user.polar_customer_id != customer_id:
        await user_repo.update(session, user, {"polar_customer_id": customer_id})


async def _notify(
    session: AsyncSession,
    user: User,
    severity: NotificationSeverity,
    title_uz: str,
    body_uz: str,
    title_en: str,
    body_en: str,
) -> None:
    await notification_service.create(
        session,
        user.id,
        kind=NotificationKind.billing,
        severity=severity,
        title={"uz": title_uz, "ru": title_en, "en": title_en},
        body={"uz": body_uz, "ru": body_en, "en": body_en},
    )


async def _handle_order_paid(session: AsyncSession, data: dict[str, object]) -> None:
    order_id = str(data.get("id") or "")
    if order_id and await billing_repo.get_invoice_by_external_id(session, order_id) is not None:
        return  # replayed delivery — already recorded
    user = await _resolve_user(session, data)
    if user is None:
        logger.warning("Polar order.paid: no matching user (order=%s)", order_id)
        return
    await _remember_customer_id(session, user, data)

    plan_id = _event_plan(data)
    amount = int(data.get("total_amount") or data.get("amount") or 0)
    now = datetime.now(UTC)
    sequence = await billing_repo.count_invoices(session) + 1
    await billing_repo.create_invoice(
        session,
        user_id=user.id,
        number=f"INV-{now.year}-{sequence:04d}",
        date=now,
        amount=amount,
        status="paid",
        plan_id=plan_id or user.plan_id,
        period=f"{now:%Y-%m}",
        external_id=order_id or None,
    )
    await _activate(session, user, data, plan_id)
    await _notify(
        session,
        user,
        NotificationSeverity.success,
        "To'lov qabul qilindi",
        f"{plan_id or user.plan_id} tarifi faollashtirildi.",
        "Payment received",
        f"The {plan_id or user.plan_id} plan is now active.",
    )


async def _handle_subscription_active(session: AsyncSession, data: dict[str, object]) -> None:
    """Subscription became active (first purchase or a renewal) — (re)entitle."""
    user = await _resolve_user(session, data)
    if user is None:
        return
    await _remember_customer_id(session, user, data)
    await _activate(session, user, data, _event_plan(data))


async def _handle_subscription_revoked(session: AsyncSession, data: dict[str, object]) -> None:
    """Subscription ended — drop to free ``start`` and clear the entitlement."""
    user = await _resolve_user(session, data)
    if user is None:
        return
    await user_repo.update(
        session, user, {"plan_id": PlanId.start.value, "plan_expires_at": None}
    )
    await _notify(
        session,
        user,
        NotificationSeverity.warn,
        "Obuna tugadi",
        "SMS yuborish to'xtatildi. Davom etish uchun tarifni qayta sotib oling.",
        "Subscription ended",
        "Sending is paused. Purchase a plan again to continue.",
    )


async def handle_event(session: AsyncSession, event: dict[str, object]) -> None:
    """Dispatch one verified webhook event; unknown types are ignored."""
    event_type = str(event.get("type") or "")
    data = event.get("data")
    if not isinstance(data, dict):
        return
    if event_type == "order.paid":
        await _handle_order_paid(session, data)
    elif event_type == "subscription.active":
        await _handle_subscription_active(session, data)
    elif event_type == "subscription.revoked":
        await _handle_subscription_revoked(session, data)
    else:
        logger.info("Polar webhook '%s' acknowledged without action", event_type)
