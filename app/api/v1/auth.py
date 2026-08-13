"""Auth routes: register, login, refresh, and the /me profile."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair, UserOut, UserUpdateIn
from app.schemas.common import CamelModel
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthOut(CamelModel):
    """Login/register response: token pair plus the profile in one trip."""

    user: UserOut
    access_token: str
    refresh_token: str


@router.post("/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
async def register(session: DbSession, body: RegisterIn) -> AuthOut:
    user, tokens = await auth_service.register(session, body)
    return AuthOut(
        user=UserOut.model_validate(user),
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


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
