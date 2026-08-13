"""SMS templates data access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import Template


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[Template]:
    stmt = (
        select(Template)
        .where(Template.user_id == user_id, Template.deleted_at.is_(None))
        .order_by(Template.updated_at.desc())
    )
    return list((await session.scalars(stmt)).all())


async def get_for_user(session: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> Template | None:
    stmt = select(Template).where(
        Template.id == template_id,
        Template.user_id == user_id,
        Template.deleted_at.is_(None),
    )
    return await session.scalar(stmt)


async def create(session: AsyncSession, **fields: Any) -> Template:
    template = Template(**fields)
    session.add(template)
    await session.flush()
    return template


async def update_fields(session: AsyncSession, template: Template, fields: dict[str, Any]) -> Template:
    for name, value in fields.items():
        setattr(template, name, value)
    await session.flush()
    return template


async def soft_delete(session: AsyncSession, template: Template) -> None:
    template.deleted_at = datetime.now(UTC)
    await session.flush()


async def increment_used(session: AsyncSession, template: Template) -> None:
    template.used_count = template.used_count + 1
    await session.flush()
