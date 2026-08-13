"""Message routes: dashboard (JWT) plus the API-key public send endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_api_key
from app.domain.enums import ApiScope
from app.infrastructure.db.models import ApiKey, User
from app.schemas.message import MessageOut, MessagesPage, SendIn
from app.services import sms_service

router = APIRouter(tags=["messages"])


@router.post("/messages", response_model=list[MessageOut], status_code=status.HTTP_201_CREATED)
async def send_messages(session: DbSession, user: CurrentUser, body: SendIn) -> list[MessageOut]:
    messages = await sms_service.send(session, user, body)
    return [MessageOut.model_validate(m) for m in messages]


@router.get("/messages", response_model=MessagesPage)
async def list_messages(
    session: DbSession,
    user: CurrentUser,
    status_: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 12,
) -> MessagesPage:
    items, total, counts = await sms_service.list_messages(
        session, user.id, status=status_, search=search, page=page, page_size=page_size
    )
    return MessagesPage(
        items=[MessageOut.model_validate(m) for m in items],
        total=total,
        counts_by_status=counts,
    )


@router.get("/messages/{message_id}", response_model=MessageOut)
async def get_message(session: DbSession, user: CurrentUser, message_id: int) -> MessageOut:
    message = await sms_service.get_message(session, user.id, message_id)
    return MessageOut.model_validate(message)


@router.post(
    "/messages/{message_id}/resend",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def resend_message(session: DbSession, user: CurrentUser, message_id: int) -> MessageOut:
    """Queue a fresh copy of an existing message (same recipient/text/priority)."""
    message = await sms_service.resend(session, user, message_id)
    return MessageOut.model_validate(message)


@router.post(
    "/public/messages",
    response_model=list[MessageOut],
    status_code=status.HTTP_201_CREATED,
    summary="Send SMS with an API key (scope: sms.send)",
)
async def public_send_messages(
    session: DbSession,
    principal: Annotated[tuple[ApiKey, User], Depends(require_api_key(ApiScope.sms_send))],
    body: SendIn,
) -> list[MessageOut]:
    """Same body as POST /messages, authenticated by ``X-API-Key``."""
    _, user = principal
    messages = await sms_service.send(session, user, body)
    return [MessageOut.model_validate(m) for m in messages]
