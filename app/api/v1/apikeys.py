"""API key management routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.apikey import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyOut
from app.services import apikey_service

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(session: DbSession, user: CurrentUser) -> list[ApiKeyOut]:
    keys = await apikey_service.list_keys(session, user.id)
    return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_key(session: DbSession, user: CurrentUser, body: ApiKeyCreateIn) -> ApiKeyCreatedOut:
    """The response carries the full secret — it is never shown again."""
    api_key, full_key = await apikey_service.create_key(session, user.id, body)
    base = ApiKeyOut.model_validate(api_key)
    return ApiKeyCreatedOut(**base.model_dump(by_alias=False), key=full_key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(session: DbSession, user: CurrentUser, key_id: uuid.UUID) -> None:
    await apikey_service.revoke_key(session, user.id, key_id)
