"""SMS message DTOs — dashboard, public API, and gateway-device protocol."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, Field, field_validator

from app.core.config import settings
from app.domain.enums import PRIORITY_RANK, FailReason, MessageStatus, SmsPriority
from app.schemas.common import CamelModel

_RANK_TO_PRIORITY: dict[int, SmsPriority] = {rank: prio for prio, rank in PRIORITY_RANK.items()}


class SendIn(CamelModel):
    """Body of POST /messages (dashboard) and POST /public/messages (API key)."""

    to: list[str] = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=1000)
    device_id: uuid.UUID | None = None
    priority: SmsPriority = SmsPriority.transactional


class MessageOut(CamelModel):
    id: int
    # ORM attribute is ``to_phone`` (column "to_phone"); wire name is "to".
    to: str = Field(validation_alias=AliasChoices("to", "to_phone"))
    contact_id: uuid.UUID | None = None
    # ORM attribute is ``text_`` (column "text").
    text: str = Field(validation_alias=AliasChoices("text", "text_"))
    status: MessageStatus
    # Stored as a smallint rank (PRIORITY_RANK); exposed as the string enum.
    priority: SmsPriority
    device_id: uuid.UUID | None = None
    segments: int
    created_at: datetime
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    fail_reason: FailReason | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def _rank_to_priority(cls, value: object) -> object:
        if isinstance(value, int):
            return _RANK_TO_PRIORITY.get(value, SmsPriority.transactional)
        return value


class MessagesPage(CamelModel):
    """GET /messages result; counts always include the ``all`` bucket."""

    items: list[MessageOut]
    total: int
    counts_by_status: dict[str, int]


class GatewayClaimIn(CamelModel):
    limit: int = Field(default=50, ge=1)

    @field_validator("limit")
    @classmethod
    def _cap_limit(cls, value: int) -> int:
        if value > settings.gateway_claim_max:
            raise ValueError(f"limit must be <= {settings.gateway_claim_max}")
        return value


class GatewayMessageOut(CamelModel):
    """What the Android gateway needs to physically send one SMS."""

    id: int
    to: str = Field(validation_alias=AliasChoices("to", "to_phone"))
    text: str = Field(validation_alias=AliasChoices("text", "text_"))
    segments: int
    # Same string enum as the rest of the API — one contract everywhere.
    priority: SmsPriority
    attempts: int
    created_at: datetime

    @field_validator("priority", mode="before")
    @classmethod
    def _rank_to_priority(cls, value: object) -> object:
        if isinstance(value, int):
            return _RANK_TO_PRIORITY.get(value, SmsPriority.transactional)
        return value


class GatewayAckIn(CamelModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class GatewayReportIn(CamelModel):
    id: int
    status: Literal["delivered", "failed"]
    fail_reason: FailReason | None = None
