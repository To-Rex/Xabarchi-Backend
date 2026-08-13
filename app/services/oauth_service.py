"""Social sign-in (Google / Apple) via the OAuth2 authorization-code flow.

The backend owns the whole redirect dance:

1. ``GET /auth/oauth/{provider}/start``    -> 302 to the provider's consent
   page; a random ``state`` goes to Redis (10 min TTL, one-time).
2. Provider redirects (Google: GET, Apple: POST form_post) to
   ``/auth/oauth/{provider}/callback`` with ``code`` + ``state``.
3. The code is exchanged for the profile (Google: userinfo endpoint;
   Apple: JWKS-verified id_token), the user is found-or-created, and the
   browser is sent to ``{FRONTEND_URL}/auth/callback#accessToken=...&
   refreshToken=...`` — tokens travel in the URL fragment so they never
   appear in server logs.

A provider is enabled only when its client id is configured.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, AuthError
from app.infrastructure.db.models import User
from app.infrastructure.redis.client import get_redis
from app.repositories import oauth_repo, user_repo

STATE_TTL_SECONDS = 600
_STATE_KEY = "oauthstate:{state}"

PROVIDERS = ("google", "apple")


@dataclass(frozen=True)
class Profile:
    """Normalized identity coming back from any provider."""

    subject: str
    email: str
    first_name: str
    last_name: str


def _redirect_uri(provider: str) -> str:
    return f"{settings.public_api_url}/api/v1/auth/oauth/{provider}/callback"


def _ensure_enabled(provider: str) -> None:
    if provider not in PROVIDERS:
        raise AppError(f"Unknown provider '{provider}'", code="unknown_provider", status=404)
    client_id = settings.google_client_id if provider == "google" else settings.apple_client_id
    if not client_id:
        raise AppError(
            f"{provider} sign-in is not configured on this server",
            code="oauth_not_configured",
            status=503,
        )


async def start(provider: str) -> str:
    """Build the provider consent URL, persisting a one-time ``state``."""
    _ensure_enabled(provider)
    state = secrets.token_urlsafe(24)
    await get_redis().set(_STATE_KEY.format(state=state), provider, ex=STATE_TTL_SECONDS)

    if provider == "google":
        query = {
            "client_id": settings.google_client_id,
            "redirect_uri": _redirect_uri(provider),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query)

    query = {
        "client_id": settings.apple_client_id,
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",  # Apple requires form_post when scopes are asked
        "state": state,
    }
    return "https://appleid.apple.com/auth/authorize?" + urlencode(query)


async def _consume_state(state: str, provider: str) -> None:
    stored = await get_redis().getdel(_STATE_KEY.format(state=state))
    if stored != provider:
        raise AuthError("OAuth state is invalid or expired")


async def _google_profile(code: str) -> Profile:
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": _redirect_uri("google"),
                "grant_type": "authorization_code",
            },
        )
        if token_response.status_code != 200:
            raise AuthError("Google code exchange failed")
        access_token = token_response.json().get("access_token", "")
        userinfo = await client.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if userinfo.status_code != 200:
        raise AuthError("Google profile fetch failed")
    data = userinfo.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise AuthError("Google account has no e-mail")
    return Profile(
        subject=str(data["sub"]),
        email=email,
        first_name=data.get("given_name") or email.split("@")[0],
        last_name=data.get("family_name") or "",
    )


async def _apple_profile(code: str) -> Profile:
    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            "https://appleid.apple.com/auth/token",
            data={
                "code": code,
                "client_id": settings.apple_client_id,
                "client_secret": settings.apple_client_secret,
                "redirect_uri": _redirect_uri("apple"),
                "grant_type": "authorization_code",
            },
        )
    if token_response.status_code != 200:
        raise AuthError("Apple code exchange failed")
    id_token = token_response.json().get("id_token", "")
    try:
        # Apple has no userinfo endpoint: verify the id_token against JWKS.
        signing_key = jwt.PyJWKClient("https://appleid.apple.com/auth/keys").get_signing_key_from_jwt(
            id_token
        )
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer="https://appleid.apple.com",
        )
    except jwt.PyJWTError as exc:
        raise AuthError("Apple id_token verification failed") from exc
    email = (claims.get("email") or "").lower()
    if not email:
        raise AuthError("Apple account shared no e-mail")
    return Profile(
        subject=str(claims["sub"]),
        email=email,
        first_name=email.split("@")[0],
        last_name="",
    )


async def complete(session: AsyncSession, provider: str, code: str, state: str) -> User:
    """Callback half: validate state, fetch the profile, find-or-create."""
    _ensure_enabled(provider)
    await _consume_state(state, provider)
    profile = await (_google_profile(code) if provider == "google" else _apple_profile(code))

    account = await oauth_repo.get_by_subject(session, provider, profile.subject)
    if account is not None:
        user = await user_repo.get_by_id(session, account.user_id)
        if user is None:
            raise AuthError("Account no longer exists")
        return user

    # First sign-in with this identity: attach to the e-mail's account, or
    # create a fresh one (provider-verified e-mail counts as verified).
    user = await user_repo.get_by_email(session, profile.email)
    if user is None:
        user = await user_repo.create(
            session,
            email=profile.email,
            password_hash=None,
            first_name=profile.first_name[:100],
            last_name=profile.last_name[:100],
            phone="",
            company="",
            avatar_hue=uuid.uuid4().int % 360,
            email_verified_at=datetime.now(UTC),
        )
    elif user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
    await oauth_repo.link(session, user_id=user.id, provider=provider, subject=profile.subject)
    return user
