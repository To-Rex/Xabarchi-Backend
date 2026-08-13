"""Outbound e-mail (password reset, e-mail verification).

SMTP settings are optional: with no ``SMTP_HOST`` configured the message is
logged instead of sent, so local development never needs a mail server and
the auth flows stay testable (the link appears in the server log).
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def _send_sync(to: str, subject: str, html: str, text: str) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(message)


async def send_email(to: str, subject: str, html: str, text: str) -> bool:
    """Send an e-mail; returns True when actually handed to SMTP.

    Never raises — mail failure must not break the auth flow that queued it.
    """
    if not settings.smtp_host:
        logger.info("SMTP not configured — e-mail to %s NOT sent. Subject: %s | %s", to, subject, text)
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, html, text)
        return True
    except Exception:  # noqa: BLE001 - log and carry on, flows stay usable
        logger.exception("Failed to send e-mail to %s (%s)", to, subject)
        return False


def link_email(title: str, intro: str, link: str, button: str) -> tuple[str, str]:
    """Tiny branded (html, text) pair around one call-to-action link."""
    html = f"""\
<div style="font-family:system-ui,sans-serif;max-width:480px;margin:0 auto;padding:24px">
  <h2 style="color:#0f766e;margin:0 0 12px">Xabarchi</h2>
  <p style="margin:0 0 8px;font-weight:600">{title}</p>
  <p style="margin:0 0 16px;color:#444">{intro}</p>
  <a href="{link}" style="display:inline-block;background:#0f766e;color:#fff;padding:10px 20px;
     border-radius:8px;text-decoration:none">{button}</a>
  <p style="margin:16px 0 0;color:#888;font-size:12px">Agar bu siz bo'lmasangiz, xatni e'tiborsiz qoldiring.</p>
</div>"""
    text = f"{title}\n\n{intro}\n{link}"
    return html, text
