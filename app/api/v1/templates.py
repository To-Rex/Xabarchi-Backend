"""SMS template routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.template import TemplateIn, TemplateOut
from app.services import template_service

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateOut])
async def list_templates(session: DbSession, user: CurrentUser) -> list[TemplateOut]:
    templates = await template_service.list_templates(session, user.id)
    return [TemplateOut.model_validate(t) for t in templates]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(session: DbSession, user: CurrentUser, body: TemplateIn) -> TemplateOut:
    template = await template_service.create_template(session, user.id, body)
    return TemplateOut.model_validate(template)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(session: DbSession, user: CurrentUser, template_id: uuid.UUID) -> TemplateOut:
    template = await template_service.get_template(session, user.id, template_id)
    return TemplateOut.model_validate(template)


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(
    session: DbSession, user: CurrentUser, template_id: uuid.UUID, body: TemplateIn
) -> TemplateOut:
    template = await template_service.update_template(session, user.id, template_id, body)
    return TemplateOut.model_validate(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(session: DbSession, user: CurrentUser, template_id: uuid.UUID) -> None:
    await template_service.delete_template(session, user.id, template_id)


@router.post("/{template_id}/used", response_model=TemplateOut)
async def mark_template_used(
    session: DbSession, user: CurrentUser, template_id: uuid.UUID
) -> TemplateOut:
    template = await template_service.mark_used(session, user.id, template_id)
    return TemplateOut.model_validate(template)
