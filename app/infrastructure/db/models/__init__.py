"""ORM models.

Importing this package registers every model on ``Base.metadata`` — Alembic's
env.py and any autogenerate run rely on this module being imported.
"""

from app.infrastructure.db.models.api_key import ApiKey
from app.infrastructure.db.models.billing import Invoice, Plan
from app.infrastructure.db.models.contact import Contact, ContactGroup, ContactGroupMember
from app.infrastructure.db.models.device import Device
from app.infrastructure.db.models.message import Message
from app.infrastructure.db.models.notification import Notification
from app.infrastructure.db.models.telegram import BotBroadcast, BotSubscriber, TelegramBot
from app.infrastructure.db.models.template import Template
from app.infrastructure.db.models.user import OAuthAccount, User

__all__ = [
    "ApiKey",
    "BotBroadcast",
    "BotSubscriber",
    "Contact",
    "ContactGroup",
    "ContactGroupMember",
    "Device",
    "Invoice",
    "Message",
    "Notification",
    "OAuthAccount",
    "Plan",
    "TelegramBot",
    "Template",
    "User",
]
