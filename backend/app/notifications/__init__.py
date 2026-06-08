"""Notification delivery — pluggable per-channel adapters.

``get_notifier(channel)`` returns the adapter for a channel, falling back to the
:class:`LogNotifier` when the channel is unconfigured so delivery degrades
gracefully (no SMTP host / no Slack webhook → the message is logged).

``deliver(...)`` is the fire-and-forget convenience used by callers that must
never fail because of a delivery error (e.g. magic-link). Scheduled reports call
``get_notifier(...).send(...)`` directly so they can record success/failure.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.notifications.base import NotificationMessage, Notifier
from app.notifications.email import EmailNotifier
from app.notifications.log import LogNotifier
from app.notifications.slack import SlackNotifier

logger = logging.getLogger("querywise")

CHANNELS = ("email", "slack", "log")


def get_notifier(channel: str) -> Notifier:
    """Return the adapter for ``channel``, or a LogNotifier if unconfigured."""
    if channel == "email":
        return EmailNotifier() if settings.smtp_host else LogNotifier("email")
    if channel == "slack":
        return SlackNotifier() if settings.slack_webhook_url else LogNotifier("slack")
    return LogNotifier(channel)


async def deliver(
    channel: str,
    *,
    subject: str,
    text_body: str,
    html_body: str | None = None,
    recipients: list[str] | None = None,
) -> bool:
    """Best-effort delivery. Returns True on success, False on failure (logged)."""
    message = NotificationMessage(
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        recipients=recipients or [],
    )
    try:
        await get_notifier(channel).send(message)
        return True
    except Exception:  # noqa: BLE001 — delivery must not crash the caller
        logger.exception("Notification delivery on channel '%s' failed", channel)
        return False


__all__ = [
    "NotificationMessage",
    "Notifier",
    "EmailNotifier",
    "SlackNotifier",
    "LogNotifier",
    "CHANNELS",
    "get_notifier",
    "deliver",
]
