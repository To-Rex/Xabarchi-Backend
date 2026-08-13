"""Gateway-device DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.domain.enums import DeviceConnection, DeviceStatus, Operator
from app.schemas.common import CamelModel


class DeviceOut(CamelModel):
    id: uuid.UUID
    name: str
    model: str
    phone: str
    operator: Operator
    status: DeviceStatus
    connection: DeviceConnection
    battery: int
    signal: int
    android_version: str
    app_version: str
    sent_today: int
    daily_limit: int
    last_seen_at: datetime | None = None
    is_default: bool


class DeviceCreateIn(CamelModel):
    """Body for pairing a new gateway phone."""

    name: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    operator: Operator
    android_version: str = Field(min_length=1, max_length=8)
    app_version: str = Field(min_length=1, max_length=16)
    daily_limit: int = Field(default=500, ge=1, le=100_000)


class DeviceUpdateIn(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, min_length=7, max_length=20)
    operator: Operator | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=100_000)


class PairOut(CamelModel):
    """Pairing result — the device token is shown exactly once."""

    device: DeviceOut
    token: str


class PairStartOut(CamelModel):
    """Short-lived pairing code the dashboard renders as a QR."""

    code: str
    # Deep-link the mobile app understands when it scans the QR.
    qr_payload: str
    expires_in: int


class PairCompleteIn(DeviceCreateIn):
    """Phone-side body: the scanned code plus the device's own details."""

    code: str = Field(min_length=8, max_length=64)


class HeartbeatIn(CamelModel):
    battery: int = Field(ge=0, le=100)
    signal: int = Field(ge=0, le=4)
    connection: DeviceConnection = DeviceConnection.polling
    sent_today: int | None = Field(default=None, ge=0)
