"""SMS template DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel


class TemplateOut(CamelModel):
    id: uuid.UUID
    name: str
    text: str
    variables: list[str]
    used_count: int
    updated_at: datetime


class TemplateIn(CamelModel):
    """Create/replace body; ``variables`` are extracted server-side."""

    name: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
