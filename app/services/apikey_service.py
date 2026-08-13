"""API key issuance, listing, revocation, and request-time verification."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError, forbidden, not_found
from app.core.security import generate_api_key, hash_token
from app.domain.enums import ApiScope
from app.infrastructure.db.models import ApiKey
from app.repositories import api_key_repo
from app.schemas.apikey import ApiKeyCreateIn


async def list_keys(session: AsyncSession, user_id: uuid.UUID) -> list[ApiKey]:
    return await api_key_repo.list_for_user(session, user_id)


async def create_key(
    session: AsyncSession, user_id: uuid.UUID, data: ApiKeyCreateIn
) -> tuple[ApiKey, str]:
    """Mint a key; the full secret is returned once and never stored."""
    full_key, prefix, key_hash = generate_api_key()
    api_key = await api_key_repo.create(
        session,
        user_id=user_id,
        name=data.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=[scope.value for scope in data.scopes],
    )
    return api_key, full_key


async def revoke_key(session: AsyncSession, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
    api_key = await api_key_repo.get_for_user(session, user_id, key_id)
    if api_key is None:
        raise not_found("API key", key_id)
    await api_key_repo.revoke(session, api_key)


async def verify(session: AsyncSession, raw_key: str, scope: ApiScope) -> ApiKey:
    """Authenticate a raw key and enforce the required scope.

    Constant work: the SHA-256 + indexed lookup path is identical whether the
    key exists or not.
    """
    api_key = await api_key_repo.get_by_hash(session, hash_token(raw_key))
    if api_key is None or api_key.revoked_at is not None:
        raise AuthError("Invalid API key")
    if scope.value not in api_key.scopes:
        raise forbidden(f"API key lacks the '{scope.value}' scope")
    await api_key_repo.touch_last_used(session, api_key)
    return api_key
