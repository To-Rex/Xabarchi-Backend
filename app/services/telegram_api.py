"""Thin async client for the Telegram Bot API (api.telegram.org).

Only the handful of methods Xabarchi needs: ``getMe`` (validate a token and read
the bot's identity on connect), ``setWebhook``/``deleteWebhook`` (subscribe to
updates), and ``sendMessage`` (broadcasts). Every call raises :class:`TelegramError`
on a non-``ok`` response so callers can translate it into an :class:`AppError`.
"""

from __future__ import annotations

from typing import Any

import httpx

_API_BASE = "https://api.telegram.org"
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


def _client() -> httpx.AsyncClient:
    # Force IPv4 egress: broken container IPv6 routes to Telegram connect but
    # never respond, which would otherwise surface as a ReadTimeout.
    return httpx.AsyncClient(
        timeout=_TIMEOUT,
        transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"),
    )


class TelegramError(Exception):
    """A Telegram API call returned ``ok: false`` (or was unreachable)."""

    def __init__(self, description: str, *, status_code: int | None = None) -> None:
        super().__init__(description)
        self.description = description
        self.status_code = status_code


async def _call(token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    url = f"{_API_BASE}/bot{token}/{method}"
    try:
        async with _client() as client:
            response = await client.post(url, json=payload or {})
    except httpx.HTTPError as exc:  # network / DNS / timeout
        raise TelegramError(f"Telegram is unreachable: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise TelegramError("Telegram returned a non-JSON response") from exc

    if not data.get("ok"):
        raise TelegramError(
            data.get("description", "Telegram API error"),
            status_code=data.get("error_code"),
        )
    return data.get("result")


async def get_me(token: str) -> dict[str, Any]:
    """Validate the token and return the bot account (id, username, first_name)."""
    return await _call(token, "getMe")


async def set_webhook(token: str, url: str, secret_token: str) -> bool:
    """Point the bot's updates at ``url``; ``secret_token`` guards the endpoint."""
    await _call(
        token,
        "setWebhook",
        {
            "url": url,
            "secret_token": secret_token,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        },
    )
    return True


async def delete_webhook(token: str) -> None:
    """Stop delivery of updates (best-effort; ignores API errors)."""
    await _call(token, "deleteWebhook", {"drop_pending_updates": False})


async def send_message(
    token: str,
    chat_id: int,
    text: str,
    *,
    button_label: str | None = None,
    button_url: str | None = None,
) -> None:
    """Send a text message, optionally with a single inline URL button."""
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": False,
    }
    if button_label and button_url:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": button_label, "url": button_url}]]
        }
    await _call(token, "sendMessage", payload)
