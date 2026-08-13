"""Reversible encryption for secrets we must replay to third parties.

Unlike API/device tokens (stored as one-way SHA-256 hashes), a Telegram bot
token has to be *used* — every ``sendMessage`` call needs the plaintext. So it
is stored encrypted-at-rest with Fernet (AES-128-CBC + HMAC) and decrypted only
in memory when a broadcast goes out.

The key is derived from ``jwt_secret`` so no extra env var is required; rotating
``jwt_secret`` therefore invalidates stored bot tokens (they must be reconnected),
which is the safe default.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    digest = hashlib.sha256(f"tg-enc:{settings.jwt_secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a secret for storage; returns a URL-safe token string."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    """Decrypt a stored secret; returns ``None`` if it can't be decrypted."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
