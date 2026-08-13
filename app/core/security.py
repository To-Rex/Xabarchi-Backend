"""Password hashing, JWT issuing/verification, and secret-token generation.

Token formats (contracts shared with the Android gateway app and the docs):

- API keys:      ``xab_live_<43 url-safe chars>`` — shown once, stored as a
                 SHA-256 hex hash plus a display prefix.
- Device tokens: ``xab_device_<43 url-safe chars>`` — same store-hash-only rule.

SHA-256 (not argon2) is used for API/device tokens because they are
high-entropy random secrets: a fast hash is safe and allows an indexed
equality lookup on every request.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.exceptions import AuthError

API_KEY_PREFIX = "xab_live_"
DEVICE_TOKEN_PREFIX = "xab_device_"
API_KEY_DISPLAY_PREFIX_LEN = 13

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a user password with argon2id (library defaults are current OWASP)."""
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its stored argon2 hash; never raises."""
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, Argon2Error):
        return False


def _encode_token(sub: str, token_type: str, ttl: timedelta, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(sub: str, extra: dict[str, Any] | None = None) -> str:
    """Issue a short-lived access token; `extra` claims must not shadow standard ones."""
    return _encode_token(
        sub,
        "access",
        timedelta(minutes=settings.access_token_ttl_minutes),
        extra,
    )


def create_refresh_token(sub: str) -> str:
    """Issue a long-lived refresh token carrying only the subject."""
    return _encode_token(sub, "refresh", timedelta(days=settings.refresh_token_ttl_days))


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a JWT, enforcing the ``type`` claim.

    Raises:
        AuthError: on expiry, bad signature, malformed token, or type mismatch.
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid token") from exc
    if payload.get("type") != expected_type:
        raise AuthError(f"Expected a {expected_type} token")
    return payload


def hash_token(token: str) -> str:
    """SHA-256 hex digest used to store/look up API keys and device tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Create a new API key.

    Returns:
        (full_key, prefix, key_hash) — the full key is shown to the user once;
        only the prefix (for display) and the hash (for lookup) are persisted.
    """
    full = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return full, full[:API_KEY_DISPLAY_PREFIX_LEN], hash_token(full)


def generate_device_token() -> tuple[str, str]:
    """Create a new gateway-device token.

    Returns:
        (full_token, token_hash) — the full token goes to the Android app once;
        only the hash is persisted.
    """
    full = DEVICE_TOKEN_PREFIX + secrets.token_urlsafe(32)
    return full, hash_token(full)
