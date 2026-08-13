"""OAuth account links data access."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import OAuthAccount


async def get_by_subject(
    session: AsyncSession, provider: str, subject: str
) -> OAuthAccount | None:
    stmt = select(OAuthAccount).where(
        OAuthAccount.provider == provider, OAuthAccount.subject == subject
    )
    return await session.scalar(stmt)


async def link(
    session: AsyncSession, *, user_id: uuid.UUID, provider: str, subject: str
) -> OAuthAccount:
    account = OAuthAccount(user_id=user_id, provider=provider, subject=subject)
    session.add(account)
    await session.flush()
    return account
