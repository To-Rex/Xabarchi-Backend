"""Domain enums.

Values mirror the frontend contracts in Xabarchi-Web
(`src/shared/mock/types.ts`) — string values are wire-format, do not rename.
"""

from __future__ import annotations

from enum import Enum


class MessageStatus(str, Enum):
    """Lifecycle of an outbound SMS."""

    queued = "queued"
    sending = "sending"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    canceled = "canceled"


class SmsPriority(str, Enum):
    """Queue class: urgent (OTP) jumps the queue; bulk is the slowest lane."""

    urgent = "urgent"
    transactional = "transactional"
    bulk = "bulk"


# Numeric rank stored in messages.priority (smallint) — lower sends first.
PRIORITY_RANK: dict[SmsPriority, int] = {
    SmsPriority.urgent: 0,
    SmsPriority.transactional: 1,
    SmsPriority.bulk: 2,
}


class DeviceStatus(str, Enum):
    online = "online"
    offline = "offline"


class DeviceConnection(str, Enum):
    """How the gateway device is linked: WebSocket, HTTP polling, or offline."""

    realtime = "realtime"
    polling = "polling"
    offline = "offline"


class Operator(str, Enum):
    """Uzbek mobile operators."""

    Ucell = "Ucell"
    Beeline = "Beeline"
    Mobiuz = "Mobiuz"
    UMS = "UMS"
    Humans = "Humans"


class BotMessageKind(str, Enum):
    """Every media shape a company bot can push to its subscribers."""

    text = "text"
    photo = "photo"
    video = "video"
    document = "document"
    post = "post"


class BroadcastStatus(str, Enum):
    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class NotificationKind(str, Enum):
    device = "device"
    billing = "billing"
    system = "system"
    sms = "sms"


class NotificationSeverity(str, Enum):
    info = "info"
    success = "success"
    warn = "warn"
    error = "error"


class PlanId(str, Enum):
    start = "start"
    biznes = "biznes"
    korxona = "korxona"


class InvoiceStatus(str, Enum):
    paid = "paid"
    due = "due"
    failed = "failed"


class FailReason(str, Enum):
    no_signal = "no_signal"
    invalid_number = "invalid_number"
    device_offline = "device_offline"


class ApiScope(str, Enum):
    """Granular permissions attachable to an API key."""

    sms_send = "sms.send"
    sms_read = "sms.read"
    devices_read = "devices.read"
    contacts_read = "contacts.read"
    telegram_send = "telegram.send"
    telegram_read = "telegram.read"
