"""Fallback notifier that logs instead of delivering.

Used when a channel is unconfigured (no SMTP host / no Slack webhook). Keeps the
scheduled-report and magic-link flows working in local dev without external
credentials — the message (and any link it carries) lands in the logs.
"""

from __future__ import annotations

import logging

from app.notifications.base import NotificationMessage, Notifier

logger = logging.getLogger("querywise")


class LogNotifier(Notifier):
    def __init__(self, channel: str = "log") -> None:
        self.channel = channel

    async def send(self, message: NotificationMessage) -> None:
        logger.info(
            "[notify:%s] to=%s subject=%r body=%s",
            self.channel,
            ", ".join(message.recipients) or "-",
            message.subject,
            message.text_body[:500],
        )
