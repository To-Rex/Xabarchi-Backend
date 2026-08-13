"""Contact and contact-group DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class ContactGroupOut(CamelModel):
    id: uuid.UUID
    name: str
    color: str


class ContactGroupIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(min_length=4, max_length=9, pattern=r"^#[0-9a-fA-F]{3,8}$")


class ContactOut(CamelModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    phone: str
    company: str | None = None
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    created_at: datetime


class ContactCreateIn(CamelModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    company: str | None = Field(default=None, max_length=255)
    group_ids: list[uuid.UUID] = Field(default_factory=list)


class ContactUpdateIn(CamelModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    company: str | None = Field(default=None, max_length=255)
    group_ids: list[uuid.UUID] | None = None
