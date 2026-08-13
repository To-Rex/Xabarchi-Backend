"""Contacts and contact groups data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Contact, ContactGroup, ContactGroupMember

# ------------------------------------------------------------------ groups


async def list_groups(session: AsyncSession, user_id: uuid.UUID) -> list[ContactGroup]:
    stmt = (
        select(ContactGroup)
        .where(ContactGroup.user_id == user_id, ContactGroup.deleted_at.is_(None))
        .order_by(ContactGroup.created_at)
    )
    return list((await session.scalars(stmt)).all())


async def get_group(session: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID) -> ContactGroup | None:
    stmt = select(ContactGroup).where(
        ContactGroup.id == group_id,
        ContactGroup.user_id == user_id,
        ContactGroup.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create_group(session: AsyncSession, user_id: uuid.UUID, name: str, color: str) -> ContactGroup:
    group = ContactGroup(user_id=user_id, name=name, color=color)
    session.add(group)
    await session.flush()
    return group


async def update_group(session: AsyncSession, group: ContactGroup, fields: dict[str, Any]) -> ContactGroup:
    for name, value in fields.items():
        setattr(group, name, value)
    await session.flush()
    return group


async def soft_delete_group(session: AsyncSession, group: ContactGroup) -> None:
    group.deleted_at = datetime.now(UTC)
    await session.execute(delete(ContactGroupMember).where(ContactGroupMember.group_id == group.id))
    await session.flush()


# ---------------------------------------------------------------- contacts


async def list_page(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    search: str | None = None,
    group_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Contact], int]:
    conditions: list[Any] = [Contact.user_id == user_id, Contact.deleted_at.is_(None)]
    if search:
        term = f"%{search.strip()}%"
        digits = "".join(ch for ch in search if ch.isdigit())
        phone_term = f"%{digits}%" if digits else term
        conditions.append(
            or_(
                Contact.first_name.ilike(term),
                Contact.last_name.ilike(term),
                Contact.phone.like(phone_term),
                Contact.company.ilike(term),
            )
        )
    if group_id is not None:
        conditions.append(
            Contact.id.in_(
                select(ContactGroupMember.contact_id).where(ContactGroupMember.group_id == group_id)
            )
        )

    total = int(
        await session.scalar(select(func.count()).select_from(Contact).where(*conditions)) or 0
    )
    stmt = (
        select(Contact)
        .where(*conditions)
        .order_by(Contact.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list((await session.scalars(stmt)).all())
    return items, total


async def get_for_user(session: AsyncSession, user_id: uuid.UUID, contact_id: uuid.UUID) -> Contact | None:
    stmt = select(Contact).where(
        Contact.id == contact_id,
        Contact.user_id == user_id,
        Contact.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create(session: AsyncSession, **fields: Any) -> Contact:
    contact = Contact(**fields)
    session.add(contact)
    await session.flush()
    return contact


async def update_fields(session: AsyncSession, contact: Contact, fields: dict[str, Any]) -> Contact:
    for name, value in fields.items():
        setattr(contact, name, value)
    await session.flush()
    return contact


async def soft_delete(session: AsyncSession, contact: Contact) -> None:
    contact.deleted_at = datetime.now(UTC)
    await session.execute(delete(ContactGroupMember).where(ContactGroupMember.contact_id == contact.id))
    await session.flush()


# -------------------------------------------------------------- membership


async def set_memberships(session: AsyncSession, contact_id: uuid.UUID, group_ids: list[uuid.UUID]) -> None:
    """Replace a contact's group memberships wholesale."""
    await session.execute(delete(ContactGroupMember).where(ContactGroupMember.contact_id == contact_id))
    for group_id in dict.fromkeys(group_ids):  # dedupe, keep order
        session.add(ContactGroupMember(contact_id=contact_id, group_id=group_id))
    await session.flush()


async def memberships_for_contacts(
    session: AsyncSession, contact_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Map contact_id -> [group_id, ...] for the given contacts."""
    if not contact_ids:
        return {}
    stmt = select(ContactGroupMember.contact_id, ContactGroupMember.group_id).where(
        ContactGroupMember.contact_id.in_(contact_ids)
    )
    result: dict[uuid.UUID, list[uuid.UUID]] = {}
    for contact_id, group_id in (await session.execute(stmt)).all():
        result.setdefault(contact_id, []).append(group_id)
    return result


async def find_by_phones(
    session: AsyncSession, user_id: uuid.UUID, phones: list[str]
) -> dict[str, uuid.UUID]:
    """Map normalized phone -> contact id (used to link sent SMS to contacts)."""
    if not phones:
        return {}
    stmt = select(Contact.phone, Contact.id).where(
        Contact.user_id == user_id,
        Contact.deleted_at.is_(None),
        Contact.phone.in_(phones),
    )
    return {phone: contact_id for phone, contact_id in (await session.execute(stmt)).all()}
