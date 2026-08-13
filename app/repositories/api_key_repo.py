"""API keys data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ApiKey


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
    """Active (non-revoked) keys, newest first."""
    stmt = (
        select(ApiKey)
        .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def get_for_user(session: AsyncSession, user_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey | None:
    stmt = select(ApiKey).where(
        ApiKey.id == key_id,
        ApiKey.user_id == user_id,
        ApiKey.revoked_at.is_(None),
    )
    return await session.scalar(stmt)


async def get_by_hash(session: AsyncSession, key_hash: str) -> ApiKey | None:
    """Lookup by SHA-256 hash — includes revoked keys; caller must check."""
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    return await session.scalar(stmt)


async def create(
    session: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    prefix: str,
    key_hash: str,
    scopes: list[str],
) -> ApiKey:
    api_key = ApiKey(user_id=user_id, name=name, prefix=prefix, key_hash=key_hash, scopes=scopes)
    session.add(api_key)
    await session.flush()
    return api_key


async def revoke(session: AsyncSession, api_key: ApiKey) -> None:
    api_key.revoked_at = datetime.now(UTC)
    await session.flush()


async def touch_last_used(session: AsyncSession, api_key: ApiKey) -> None:
    api_key.last_used_at = datetime.now(UTC)
    await session.flush()
