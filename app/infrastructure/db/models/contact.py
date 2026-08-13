"""Contacts, contact groups, and their many-to-many membership."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class ContactGroup(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "contact_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # CSS color, up to #RRGGBBAA.
    color: Mapped[str] = mapped_column(String(9), nullable=False)


class Contact(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_user_phone", "user_id", "phone"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ContactGroupMember(Base):
    """Join table; CASCADE here is safe — membership is not user data itself."""

    __tablename__ = "contact_group_members"

    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contact_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
