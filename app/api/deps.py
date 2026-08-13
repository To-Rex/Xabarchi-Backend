"""FastAPI dependencies: DB session and the three authentication schemes.

1. ``get_current_user``   — Bearer JWT access token (dashboard).
2. ``get_device``         — ``X-Device-Token`` header (Android gateway app).
3. ``require_api_key``    — ``X-API-Key`` header or Bearer ``xab_live_...``
                            (public API), parameterized by required scope.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthError
from app.core.security import API_KEY_PREFIX, decode_token, hash_token
from app.domain.enums import ApiScope
from app.infrastructure.db.models import ApiKey, Device, User
from app.infrastructure.db.session import get_session
from app.repositories import device_repo, user_repo
from app.services import apikey_service

# Re-exported name used by every router.
get_db = get_session

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthError("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Expected 'Authorization: Bearer <token>'")
    return token.strip()


async def get_current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Authenticate the dashboard user from a Bearer JWT access token."""
    payload = decode_token(_bearer_token(authorization), "access")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise AuthError("Invalid token subject") from exc
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise AuthError("Account no longer exists")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_device(
    session: DbSession,
    x_device_token: Annotated[str | None, Header()] = None,
) -> Device:
    """Authenticate a gateway device from its ``X-Device-Token`` header."""
    if not x_device_token:
        raise AuthError("Missing X-Device-Token header")
    device = await device_repo.get_by_token_hash(session, hash_token(x_device_token.strip()))
    if device is None:
        raise AuthError("Invalid device token")
    return device


GatewayDevice = Annotated[Device, Depends(get_device)]


def require_api_key(scope: ApiScope) -> Callable[..., Awaitable[tuple[ApiKey, User]]]:
    """Dependency factory: authenticate an API key carrying ``scope``.

    The key may arrive as ``X-API-Key: xab_live_...`` or as a Bearer token.
    Resolves to ``(api_key, owning_user)``.
    """

    async def dependency(
        session: DbSession,
        x_api_key: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ) -> tuple[ApiKey, User]:
        raw = (x_api_key or "").strip()
        if not raw and authorization:
            candidate = _bearer_token(authorization)
            if candidate.startswith(API_KEY_PREFIX):
                raw = candidate
        if not raw:
            raise AuthError("Missing API key (X-API-Key header or Bearer xab_live_...)")
        api_key = await apikey_service.verify(session, raw, scope)
        user = await user_repo.get_by_id(session, api_key.user_id)
        if user is None:
            raise AuthError("Key owner account no longer exists")
        return api_key, user

    return dependency
