"""Message routes: dashboard (JWT) plus the API-key public send endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DbSession, require_api_key
from app.domain.enums import ApiScope
from app.infrastructure.db.models import ApiKey, User
from app.schemas.message import (
    BulkActionIn,
    BulkResultOut,
    ClearIn,
    MessageOut,
    MessagesPage,
    SendIn,
)
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


@router.post("/messages/{message_id}/cancel", response_model=MessageOut)
async def cancel_message(session: DbSession, user: CurrentUser, message_id: int) -> MessageOut:
    """Cancel a still-queued message so the gateway never sends it."""
    message = await sms_service.cancel(session, user, message_id)
    return MessageOut.model_validate(message)


@router.post("/messages/bulk", response_model=BulkResultOut)
async def bulk_action(session: DbSession, user: CurrentUser, body: BulkActionIn) -> BulkResultOut:
    """Cancel, delete, or re-prioritize many selected messages at once."""
    affected = await sms_service.bulk_action(session, user, body.ids, body.action, body.priority)
    return BulkResultOut(affected=affected)


@router.post("/messages/clear", response_model=BulkResultOut)
async def clear_messages(session: DbSession, user: CurrentUser, body: ClearIn) -> BulkResultOut:
    """Delete all of the user's messages (optionally only one status)."""
    status_value = body.status.value if body.status else None
    affected = await sms_service.clear_all(session, user, status_value)
    return BulkResultOut(affected=affected)


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


@router.get(
    "/public/messages",
    response_model=MessagesPage,
    summary="List messages with an API key (scope: sms.read)",
)
async def public_list_messages(
    session: DbSession,
    principal: Annotated[tuple[ApiKey, User], Depends(require_api_key(ApiScope.sms_read))],
    status_: Annotated[str | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> MessagesPage:
    """List messages, authenticated by ``X-API-Key`` (scope ``sms.read``).

    Filter by ``status`` to fetch what wasn't delivered: ``failed`` (couldn't be
    sent) or ``queued`` (still waiting). ``countsByStatus`` gives per-status totals.
    """
    _, user = principal
    items, total, counts = await sms_service.list_messages(
        session, user.id, status=status_, search=search, page=page, page_size=page_size
    )
    return MessagesPage(
        items=[MessageOut.model_validate(m) for m in items],
        total=total,
        counts_by_status=counts,
    )
