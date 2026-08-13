"""Registration, login, token refresh, profile updates, password reset,
and e-mail verification."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.infrastructure.db.models import User
from app.infrastructure.redis.client import get_redis
from app.repositories import user_repo
from app.schemas.auth import LoginIn, RegisterIn, TokenPair, UserUpdateIn
from app.services import email_service

logger = logging.getLogger(__name__)

# One-time tokens live in Redis: pwdreset:{token} / emailverify:{token} -> user_id.
_RESET_KEY = "pwdreset:{token}"
_VERIFY_KEY = "emailverify:{token}"
RESET_TTL_SECONDS = 30 * 60
VERIFY_TTL_SECONDS = 24 * 60 * 60


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
    await send_verification_email(user)
    return user, _token_pair(user.id)


async def login(session: AsyncSession, data: LoginIn) -> tuple[User, TokenPair]:
    user = await user_repo.get_by_email(session, data.email)
    # Social-only accounts (password_hash is NULL) can't password-login.
    if user is None or user.password_hash is None or not verify_password(
        data.password, user.password_hash
    ):
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


def issue_tokens(user_id: uuid.UUID) -> TokenPair:
    """Public token-pair mint used by the social-auth callback."""
    return _token_pair(user_id)


# ------------------------------------------------------- password reset


async def request_password_reset(session: AsyncSession, email: str) -> None:
    """Always succeeds silently — never reveals whether the e-mail exists."""
    user = await user_repo.get_by_email(session, email)
    if user is None or user.password_hash is None:
        return
    token = secrets.token_urlsafe(32)
    await get_redis().set(_RESET_KEY.format(token=token), str(user.id), ex=RESET_TTL_SECONDS)
    link = f"{settings.frontend_url}/reset-password?token={token}"
    html, text = email_service.link_email(
        "Parolni tiklash",
        "Xabarchi hisobingiz parolini tiklash uchun tugmani bosing. Havola 30 daqiqa amal qiladi.",
        link,
        "Parolni tiklash",
    )
    await email_service.send_email(user.email, "Xabarchi — parolni tiklash", html, text)


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    """GETDEL keeps the token strictly one-time even under races."""
    user_id_raw = await get_redis().getdel(_RESET_KEY.format(token=token))
    if not user_id_raw:
        raise AuthError("Reset token is invalid or expired")
    user = await user_repo.get_by_id(session, uuid.UUID(user_id_raw))
    if user is None:
        raise AuthError("Reset token is invalid or expired")
    await user_repo.update(session, user, {"password_hash": hash_password(new_password)})


# ---------------------------------------------------- e-mail verification


async def send_verification_email(user: User) -> None:
    """Queue a verification mail; never raises (registration must succeed)."""
    if user.email_verified_at is not None:
        return
    try:
        token = secrets.token_urlsafe(32)
        await get_redis().set(_VERIFY_KEY.format(token=token), str(user.id), ex=VERIFY_TTL_SECONDS)
        link = f"{settings.frontend_url}/verify-email?token={token}"
        html, text = email_service.link_email(
            "E-mailni tasdiqlash",
            "Xabarchi hisobingizni faollashtirish uchun e-mail manzilingizni tasdiqlang.",
            link,
            "Tasdiqlash",
        )
        await email_service.send_email(user.email, "Xabarchi — e-mailni tasdiqlang", html, text)
    except Exception:  # noqa: BLE001 - mail is best-effort, auth flow is not
        logger.exception("Could not queue verification e-mail for %s", user.email)


async def verify_email(session: AsyncSession, token: str) -> User:
    user_id_raw = await get_redis().getdel(_VERIFY_KEY.format(token=token))
    if not user_id_raw:
        raise AuthError("Verification token is invalid or expired")
    user = await user_repo.get_by_id(session, uuid.UUID(user_id_raw))
    if user is None:
        raise AuthError("Verification token is invalid or expired")
    if user.email_verified_at is None:
        await user_repo.update(session, user, {"email_verified_at": datetime.now(UTC)})
    return user
