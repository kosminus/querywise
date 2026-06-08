"""SMTP email notifier (stdlib ``smtplib``, no extra dependency).

``smtplib`` is synchronous, so the blocking send runs in a worker thread via
``asyncio.to_thread`` to avoid stalling the event loop.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from app.config import settings
from app.notifications.base import NotificationMessage, Notifier


class EmailNotifier(Notifier):
    channel = "email"

    async def send(self, message: NotificationMessage) -> None:
        if not message.recipients:
            raise ValueError("Email delivery requires at least one recipient.")
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: NotificationMessage) -> None:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = settings.smtp_from
        email["To"] = ", ".join(message.recipients)
        email.set_content(message.text_body)
        if message.html_body:
            email.add_alternative(message.html_body, subtype="html")

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password or "")
            smtp.send_message(email)
