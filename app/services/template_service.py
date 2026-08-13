"""SMS template management with {variable} extraction."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import not_found
from app.infrastructure.db.models import Template
from app.repositories import template_repo
from app.schemas.template import TemplateIn

# {ism}, {kod_2}, unicode letters allowed; whitespace/braces inside are not.
_VARIABLE_RE = re.compile(r"\{([^\s{}]+)\}")


def extract_variables(text: str) -> list[str]:
    """Ordered, de-duplicated {placeholder} names found in the text."""
    return list(dict.fromkeys(_VARIABLE_RE.findall(text)))


async def list_templates(session: AsyncSession, user_id: uuid.UUID) -> list[Template]:
    return await template_repo.list_for_user(session, user_id)


async def get_template(session: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> Template:
    template = await template_repo.get_for_user(session, user_id, template_id)
    if template is None:
        raise not_found("Template", template_id)
    return template


async def create_template(session: AsyncSession, user_id: uuid.UUID, data: TemplateIn) -> Template:
    return await template_repo.create(
        session,
        user_id=user_id,
        name=data.name,
        text=data.text,
        variables=extract_variables(data.text),
    )


async def update_template(
    session: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID, data: TemplateIn
) -> Template:
    template = await get_template(session, user_id, template_id)
    return await template_repo.update_fields(
        session,
        template,
        {"name": data.name, "text": data.text, "variables": extract_variables(data.text)},
    )


async def delete_template(session: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> None:
    template = await get_template(session, user_id, template_id)
    await template_repo.soft_delete(session, template)


async def mark_used(session: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> Template:
    template = await get_template(session, user_id, template_id)
    await template_repo.increment_used(session, template)
    return template
