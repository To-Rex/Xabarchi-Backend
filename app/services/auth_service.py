"""Registration, login, token refresh, and profile updates."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.infrastructure.db.models import User
from app.repositories import user_repo
from app.schemas.auth import LoginIn, RegisterIn, TokenPair, UserUpdateIn


def _token_pair(user_id: uuid.UUID) -> TokenPair:
    sub = str(user_id)
    return TokenPair(
        access_token=create_access_token(sub),
        refresh_token=create_refresh_token(sub),
    )


async def register(session: AsyncSession, data: RegisterIn) -> tuple[User, TokenPair]:
    """Create an account on the free plan and issue the first token pair."""
    existing = await user_repo.get_by_email(session, data.email)
    if existing is not None:
        raise AppError("Email is already registered", code="email_taken", status=409)
    user = await user_repo.create(
        session,
        email=data.email,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        company=data.company,
    )
    return user, _token_pair(user.id)


async def login(session: AsyncSession, data: LoginIn) -> tuple[User, TokenPair]:
    user = await user_repo.get_by_email(session, data.email)
    if user is None or not verify_password(data.password, user.password_hash):
        # One message for both cases — never reveal whether the email exists.
        raise AuthError("Invalid email or password")
    return user, _token_pair(user.id)


async def refresh(session: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token, "refresh")
    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except ValueError as exc:
        raise AuthError("Invalid token subject") from exc
    user = await user_repo.get_by_id(session, user_id)
    if user is None:
        raise AuthError("Account no longer exists")
    return _token_pair(user.id)


async def update_profile(session: AsyncSession, user: User, data: UserUpdateIn) -> User:
    fields = data.model_dump(exclude_none=True)
    if not fields:
        return user
    return await user_repo.update(session, user, fields)
