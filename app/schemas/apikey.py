"""API key DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.enums import ApiScope
from app.schemas.common import CamelModel


class ApiKeyCreateIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[ApiScope] = Field(min_length=1)


class ApiKeyOut(CamelModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    scopes: list[ApiScope]


class ApiKeyCreatedOut(ApiKeyOut):
    """Creation response — carries the full secret exactly once."""

    key: str
