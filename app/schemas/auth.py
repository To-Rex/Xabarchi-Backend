"""Auth and user-profile DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field, field_validator

from app.domain.enums import PlanId
from app.schemas.common import CamelModel

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(CamelModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=255, pattern=_EMAIL_PATTERN)
    phone: str = Field(min_length=7, max_length=20)
    company: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginIn(CamelModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, value: str) -> str:
        return value.strip().lower()


class RefreshIn(CamelModel):
    refresh_token: str = Field(min_length=1)


class TokenPair(CamelModel):
    access_token: str
    refresh_token: str


class UserOut(CamelModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    phone: str
    company: str
    role: str
    avatar_hue: int
    plan_id: PlanId
    created_at: datetime
    timezone: str


class UserUpdateIn(CamelModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    company: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    avatar_hue: int | None = Field(default=None, ge=0, le=360)
