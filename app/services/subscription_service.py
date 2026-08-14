"""Plan resolution for limit enforcement.

Xabarchi has a free tier: the ``start`` plan always works within its own caps
(1 device, 500 SMS/month). Paid plans (``biznes``/``korxona``) unlock bigger
caps while their subscription is live; once it lapses the account falls back to
``start`` limits — not blocked, just downgraded — until it's renewed.

So every quota check runs against the *effective* plan, resolved here.
"""

from __future__ import annotations

from app.domain.enums import PlanId
from app.infrastructure.db.models import User


def effective_plan_id(user: User) -> str:
    """The plan whose limits actually apply right now.

    The user's paid plan while its subscription is active; otherwise the free
    ``start`` plan (covers both brand-new accounts and lapsed paid ones).
    """
    return user.plan_id if user.plan_active else PlanId.start.value
