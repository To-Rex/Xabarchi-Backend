"""The paywall gate: paid features require a live subscription.

Xabarchi is subscription-only — sending SMS and enrolling gateway devices are
blocked unless the account holds an active paid plan (``User.plan_active``).
When a plan lapses (``plan_expires_at`` passes) the account is blocked until it
is re-purchased or renewed, no cron needed: the check is evaluated per request.
"""

from __future__ import annotations

from app.core.exceptions import SubscriptionError
from app.infrastructure.db.models import User


def assert_active(user: User) -> None:
    """Raise :class:`SubscriptionError` (402) unless the plan is active."""
    if not user.plan_active:
        raise SubscriptionError(
            "An active subscription is required — purchase or renew a plan to continue."
        )
