"""Contact and contact-group routes."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.contact import (
    ContactCreateIn,
    ContactGroupIn,
    ContactGroupOut,
    ContactOut,
    ContactUpdateIn,
)
from app.services import contact_service

router = APIRouter(prefix="/contacts", tags=["contacts"])

# ------------------------------------------------------------------ groups
# NOTE: /contacts/groups must be declared before /contacts/{contact_id}.


@router.get("/groups", response_model=list[ContactGroupOut])
async def list_groups(session: DbSession, user: CurrentUser) -> list[ContactGroupOut]:
    groups = await contact_service.list_groups(session, user.id)
    return [ContactGroupOut.model_validate(g) for g in groups]


@router.post("/groups", response_model=ContactGroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(session: DbSession, user: CurrentUser, body: ContactGroupIn) -> ContactGroupOut:
    group = await contact_service.create_group(session, user.id, body)
    return ContactGroupOut.model_validate(group)


@router.put("/groups/{group_id}", response_model=ContactGroupOut)
async def update_group(
    session: DbSession, user: CurrentUser, group_id: uuid.UUID, body: ContactGroupIn
) -> ContactGroupOut:
    group = await contact_service.update_group(session, user.id, group_id, body)
    return ContactGroupOut.model_validate(group)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(session: DbSession, user: CurrentUser, group_id: uuid.UUID) -> None:
    await contact_service.delete_group(session, user.id, group_id)


# ---------------------------------------------------------------- contacts


@router.get("", response_model=Page[ContactOut])
async def list_contacts(
    session: DbSession,
    user: CurrentUser,
    search: Annotated[str | None, Query(max_length=200)] = None,
    group_id: Annotated[uuid.UUID | None, Query(alias="groupId")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200, alias="pageSize")] = 50,
) -> Page[ContactOut]:
    items, total = await contact_service.list_contacts(
        session, user.id, search=search, group_id=group_id, page=page, page_size=page_size
    )
    return Page[ContactOut](items=items, total=total)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(session: DbSession, user: CurrentUser, body: ContactCreateIn) -> ContactOut:
    return await contact_service.create_contact(session, user.id, body)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(session: DbSession, user: CurrentUser, contact_id: uuid.UUID) -> ContactOut:
    return await contact_service.get_contact(session, user.id, contact_id)


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    session: DbSession, user: CurrentUser, contact_id: uuid.UUID, body: ContactUpdateIn
) -> ContactOut:
    return await contact_service.update_contact(session, user.id, contact_id, body)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(session: DbSession, user: CurrentUser, contact_id: uuid.UUID) -> None:
    await contact_service.delete_contact(session, user.id, contact_id)
