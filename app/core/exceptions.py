"""Application error hierarchy.

Every expected failure is an :class:`AppError` carrying a stable machine
``code`` (for API clients), a human ``message``, and the HTTP status to map
to. Routers/services raise these; a single exception handler in `app.main`
turns them into JSON responses — keeping HTTP concerns out of the domain.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""

    code: str = "app_error"
    status: int = 400

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status

    def to_dict(self) -> dict[str, str]:
        """Serializable payload for the API error envelope."""
        return {"code": self.code, "message": self.message}


class NotFoundError(AppError):
    """Requested resource does not exist (or is soft-deleted)."""

    code = "not_found"
    status = 404


class AuthError(AppError):
    """Authentication or authorization failed."""

    code = "auth_error"
    status = 401


class QuotaError(AppError):
    """Plan quota exceeded (monthly SMS, device count, etc.)."""

    code = "quota_exceeded"
    status = 402


class RateLimitError(AppError):
    """Too many requests for this principal."""

    code = "rate_limited"
    status = 429


def not_found(resource: str, identifier: object) -> NotFoundError:
    """Uniform not-found message: ``not_found('Device', id)``."""
    return NotFoundError(f"{resource} {identifier!s} not found")


def forbidden(message: str = "Insufficient permissions") -> AuthError:
    """AuthError preset to HTTP 403 for scope/ownership violations."""
    return AuthError(message, code="forbidden", status=403)
