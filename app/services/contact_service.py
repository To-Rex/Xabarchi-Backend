"""Contacts and contact-group management."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.infrastructure.db.models import Contact, ContactGroup
from app.repositories import contact_repo
from app.schemas.contact import (
    ContactCreateIn,
    ContactGroupIn,
    ContactOut,
    ContactUpdateIn,
)
from app.services.sms_service import normalize_phone

# ------------------------------------------------------------------ groups


async def list_groups(session: AsyncSession, user_id: uuid.UUID) -> list[ContactGroup]:
    return await contact_repo.list_groups(session, user_id)


async def create_group(session: AsyncSession, user_id: uuid.UUID, data: ContactGroupIn) -> ContactGroup:
    return await contact_repo.create_group(session, user_id, data.name, data.color)


async def update_group(
    session: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID, data: ContactGroupIn
) -> ContactGroup:
    group = await contact_repo.get_group(session, user_id, group_id)
    if group is None:
        raise not_found("Contact group", group_id)
    return await contact_repo.update_group(session, group, {"name": data.name, "color": data.color})


async def delete_group(session: AsyncSession, user_id: uuid.UUID, group_id: uuid.UUID) -> None:
    group = await contact_repo.get_group(session, user_id, group_id)
    if group is None:
        raise not_found("Contact group", group_id)
    await contact_repo.soft_delete_group(session, group)


# ---------------------------------------------------------------- contacts


async def _validate_group_ids(
    session: AsyncSession, user_id: uuid.UUID, group_ids: list[uuid.UUID]
) -> None:
    for group_id in group_ids:
        if await contact_repo.get_group(session, user_id, group_id) is None:
            raise not_found("Contact group", group_id)


async def list_contacts(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    search: str | None = None,
    group_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ContactOut], int]:
    contacts, total = await contact_repo.list_page(
        session, user_id, search=search, group_id=group_id, page=page, page_size=page_size
    )
    memberships = await contact_repo.memberships_for_contacts(session, [c.id for c in contacts])
    items = [_to_out(contact, memberships.get(contact.id, [])) for contact in contacts]
    return items, total


async def get_contact(session: AsyncSession, user_id: uuid.UUID, contact_id: uuid.UUID) -> ContactOut:
    contact = await contact_repo.get_for_user(session, user_id, contact_id)
    if contact is None:
        raise not_found("Contact", contact_id)
    memberships = await contact_repo.memberships_for_contacts(session, [contact.id])
    return _to_out(contact, memberships.get(contact.id, []))


async def create_contact(session: AsyncSession, user_id: uuid.UUID, data: ContactCreateIn) -> ContactOut:
    await _validate_group_ids(session, user_id, data.group_ids)
    contact = await contact_repo.create(
        session,
        user_id=user_id,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=normalize_phone(data.phone),
        company=data.company,
    )
    await contact_repo.set_memberships(session, contact.id, data.group_ids)
    return _to_out(contact, data.group_ids)


async def update_contact(
    session: AsyncSession, user_id: uuid.UUID, contact_id: uuid.UUID, data: ContactUpdateIn
) -> ContactOut:
    contact = await contact_repo.get_for_user(session, user_id, contact_id)
    if contact is None:
        raise not_found("Contact", contact_id)
    fields = data.model_dump(exclude_none=True, exclude={"group_ids"})
    if "phone" in fields:
        fields["phone"] = normalize_phone(fields["phone"])
    if fields:
        contact = await contact_repo.update_fields(session, contact, fields)
    if data.group_ids is not None:
        await _validate_group_ids(session, user_id, data.group_ids)
        await contact_repo.set_memberships(session, contact.id, data.group_ids)
    memberships = await contact_repo.memberships_for_contacts(session, [contact.id])
    return _to_out(contact, memberships.get(contact.id, []))


async def delete_contact(session: AsyncSession, user_id: uuid.UUID, contact_id: uuid.UUID) -> None:
    contact = await contact_repo.get_for_user(session, user_id, contact_id)
    if contact is None:
        raise not_found("Contact", contact_id)
    await contact_repo.soft_delete(session, contact)


def _to_out(contact: Contact, group_ids: list[uuid.UUID]) -> ContactOut:
    return ContactOut(
        id=contact.id,
        first_name=contact.first_name,
        last_name=contact.last_name,
        phone=contact.phone,
        company=contact.company,
        group_ids=group_ids,
        created_at=contact.created_at,
    )
