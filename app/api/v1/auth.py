"""Auth routes: register, login, refresh, /me profile, password reset,
e-mail verification, and social sign-in (Google / Apple)."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.auth import (
    ForgotPasswordIn,
    LoginIn,
    MessageOut,
    RefreshIn,
    RegisterIn,
    ResendVerificationIn,
    ResetPasswordIn,
    TokenPair,
    UserOut,
    UserUpdateIn,
    VerifyEmailIn,
)
from app.schemas.common import CamelModel
from app.services import auth_service, oauth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthOut(CamelModel):
    """Login/register response: token pair plus the profile in one trip."""

    user: UserOut
    access_token: str
    refresh_token: str


@router.post("/register", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def register(session: DbSession, body: RegisterIn) -> MessageOut:
    """Create the account and e-mail a verification link. No session is issued:
    the user signs in only after confirming their e-mail."""
    await auth_service.register(session, body)
    return MessageOut(message="Account created — check your e-mail to verify your address")


@router.post("/login", response_model=AuthOut)
async def login(session: DbSession, body: LoginIn) -> AuthOut:
    user, tokens = await auth_service.login(session, body)
    return AuthOut(
        user=UserOut.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(session: DbSession, body: RefreshIn) -> TokenPair:
    return await auth_service.refresh(session, body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(session: DbSession, user: CurrentUser, body: UserUpdateIn) -> UserOut:
    updated = await auth_service.update_profile(session, user, body)
    return UserOut.model_validate(updated)


# ------------------------------------------------------- password reset


@router.post("/password/forgot", response_model=MessageOut)
async def forgot_password(session: DbSession, body: ForgotPasswordIn) -> MessageOut:
    """Always 200 — the response never reveals whether the e-mail exists."""
    await auth_service.request_password_reset(session, body.email)
    return MessageOut(message="If the e-mail exists, a reset link has been sent")


@router.post("/password/reset", response_model=MessageOut)
async def reset_password(session: DbSession, body: ResetPasswordIn) -> MessageOut:
    await auth_service.reset_password(session, body.token, body.password)
    return MessageOut(message="Password has been reset")


# ---------------------------------------------------- e-mail verification


@router.post("/email/verify", response_model=UserOut)
async def verify_email(session: DbSession, body: VerifyEmailIn) -> UserOut:
    user = await auth_service.verify_email(session, body.token)
    return UserOut.model_validate(user)


@router.post("/email/resend", response_model=MessageOut)
async def resend_verification(session: DbSession, body: ResendVerificationIn) -> MessageOut:
    """Unauthenticated — a blocked (unverified) user has no session to resend
    from. Always 200 so it can't be used to probe which e-mails exist."""
    await auth_service.resend_verification(session, body.email)
    return MessageOut(message="If the account exists and is unverified, a verification e-mail has been sent")


# ------------------------------------------------- social sign-in (OAuth)


@router.get("/oauth/{provider}/start", include_in_schema=True)
async def oauth_start(provider: str, request: Request, redirect: str = "") -> RedirectResponse:
    """302 to the provider's consent screen (Google / Apple).

    ``?redirect=<origin>`` (or the Referer/Origin header) records where to return
    the tokens; the service allow-lists it, so localhost and prod each come back
    to themselves.
    """
    return_url = redirect or request.headers.get("referer") or request.headers.get("origin") or ""
    url = await oauth_service.start(provider, return_url)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


async def _oauth_finish(session: DbSession, provider: str, code: str, state: str) -> RedirectResponse:
    """Shared callback: exchange the code, then hand tokens to the frontend.

    Tokens travel in the URL *fragment* so they never reach server logs;
    errors land on the same page as ``#error=<code>``.
    """
    try:
        user, origin = await oauth_service.complete(session, provider, code, state)
    except AppError as exc:
        # State (which carries the origin) is gone on failure — fall back to
        # the configured frontend for the error screen.
        return RedirectResponse(
            f"{settings.frontend_url.rstrip('/')}/auth/callback#error={quote(exc.code)}",
            status_code=status.HTTP_302_FOUND,
        )
    tokens = auth_service.issue_tokens(user.id)
    fragment = f"accessToken={quote(tokens.access_token)}&refreshToken={quote(tokens.refresh_token)}"
    return RedirectResponse(
        f"{origin}/auth/callback#{fragment}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/oauth/{provider}/callback", include_in_schema=False)
async def oauth_callback_get(
    session: DbSession, provider: str, code: str = "", state: str = ""
) -> RedirectResponse:
    return await _oauth_finish(session, provider, code, state)


@router.post("/oauth/{provider}/callback", include_in_schema=False)
async def oauth_callback_post(
    session: DbSession, provider: str, request: Request
) -> RedirectResponse:
    """Apple posts the code back as an HTML form (``response_mode=form_post``)."""
    form = await request.form()
    return await _oauth_finish(
        session, provider, str(form.get("code") or ""), str(form.get("state") or "")
    )
